"""
车辆知识库 — FAISS 向量检索 + RAG 问答
==========================================
B岗核心模块：负责车辆说明书、故障码、车载功能文档的语义检索。

功能：
  1. 自动加载/构建 FAISS 向量索引
  2. 语义检索：根据用户查询返回相关文档片段
  3. 与 interaction_agent 对接，提供知识上下文
  4. 离线降级：无索引时返回预设兜底文本

输出 dict 格式：
  {
    "success": bool,
    "query": str,
    "docs": [{"content": str, "source": str, "score": float}],
    "fallback_msg": str
  }
"""

import os
from __future__ import annotations
import logging
import pickle
from typing import Optional

logger = logging.getLogger(__name__)

# ── 路径常量 ──
_KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "knowledge")
_INDEX_DIR = os.path.join(_KNOWLEDGE_DIR, "faiss_index")
_INDEX_FILE = os.path.join(_INDEX_DIR, "index.faiss")
_META_FILE = os.path.join(_INDEX_DIR, "metadata.pkl")


class VehicleKnowledgeBase:
    """车辆知识库 — FAISS + Embeddings 语义检索"""

    # ── 离线兜底知识（网络不可用 / 索引不存在时的最小可用回复）──
    FALLBACK_KNOWLEDGE: dict[str, str] = {
        "空调": "空调控制：语音说「打开空调」启动，支持 16-30°C 范围，风速 1-5 档。",
        "音乐": "影音娱乐：语音说「播放音乐」开始播放，支持暂停/切歌/音量调节。",
        "导航": "导航系统：语音说「导航到 + 目的地」即可开始路线规划。",
        "胎压": "胎压标准：前轮 2.3-2.5 bar，后轮 2.2-2.4 bar。警告灯亮请立即检查。",
        "故障": "若仪表盘故障灯亮起，请参考车辆说明书或联系售后服务中心。",
        "发动机": "发动机故障灯亮起时，建议减速行驶并尽快到店检测。红灯亮起请立即安全停车。",
        "制动": "制动系统警告灯亮起表示制动液不足或系统故障，请立即安全停车并联系救援。",
        "机油": "机油压力警告灯亮起表示机油压力不足，请立即安全停车，检查机油液位。",
        "电池": "12V 蓄电池电压异常可能导致启动困难，建议检查电池状态或更换。",
        "车窗": "车窗控制：语音说「打开主驾车窗」或「关闭全部车窗」即可操作。",
        "座椅": "座椅调节：支持加热、通风、按摩功能，语音说「打开座椅加热」启用。",
        "天窗": "天窗控制：语音说「打开天窗」或「关闭天窗」即可操作。",
    }

    def __init__(self, index_path: str = _INDEX_DIR):
        """初始化知识库，尝试加载已有索引，不存在则自动构建"""
        self.index_path = index_path
        self.documents: list[dict] = []       # [{"content": str, "source": str}, ...]
        self.index = None                      # FAISS 索引
        self.embedding_fn = None               # embedding 函数
        self._offline = False                  # 离线标记
        self._loaded = False

        self._ensure_dirs()
        self._load_or_build()

    # ── 公共接口 ──

    def retrieve_knowledge(self, query: str, top_k: int = 3) -> dict:
        """
        根据查询文本检索车辆相关知识。

        Args:
            query: 用户查询文本（语音/手势转换后的文字）
            top_k: 返回最相关文档片段数量

        Returns:
            {
                "success": bool,
                "query": str,
                "docs": [{"content": str, "source": str, "score": float}],
                "fallback_msg": str
            }
        """
        result = {
            "success": False,
            "query": query or "",
            "docs": [],
            "fallback_msg": "",
        }

        if not query or not query.strip():
            result["fallback_msg"] = "未输入查询内容，请描述您遇到的问题。"
            return result

        query = query.strip()

        # 尝试 FAISS 检索
        if self.index is not None and self._loaded:
            try:
                docs = self._search(query, top_k)
                if docs:
                    result["success"] = True
                    result["docs"] = docs
                    return result
            except Exception as e:
                logger.warning(f"FAISS 检索异常: {e}，降级到关键词匹配")

        # 降级：关键词匹配
        fallback_docs = self._keyword_match(query, top_k)
        if fallback_docs:
            result["success"] = True
            result["docs"] = fallback_docs
            result["fallback_msg"] = "（离线模式：基于本地关键词匹配）"
        else:
            result["fallback_msg"] = self._get_fallback_msg(query)

        return result

    def build_vector_store(self, force: bool = False) -> dict:
        """
        重建向量库。支持手动更新知识库后调用。

        Returns:
            {"success": bool, "doc_count": int, "message": str}
        """
        if force:
            self.index = None
            self.documents = []
            self._loaded = False

        try:
            self._build_index()
            return {
                "success": True,
                "doc_count": len(self.documents),
                "message": f"向量库已重建，共 {len(self.documents)} 条文档",
            }
        except Exception as e:
            logger.error(f"向量库重建失败: {e}")
            return {"success": False, "doc_count": 0, "message": f"重建失败: {str(e)}"}

    def get_status(self) -> dict:
        """获取知识库状态"""
        return {
            "loaded": self._loaded,
            "offline": self._offline,
            "index_path": self.index_path,
            "doc_count": len(self.documents),
            "faiss_available": self.index is not None,
        }

    # ── 内部实现 ──

    def _ensure_dirs(self):
        """确保目录存在"""
        os.makedirs(self.index_path, exist_ok=True)

    def _load_or_build(self):
        """尝试加载已有索引，失败则重建"""
        if os.path.exists(_INDEX_FILE) and os.path.exists(_META_FILE):
            try:
                self._load_index()
                logger.info(f"FAISS 索引已加载: {len(self.documents)} 条文档")
                return
            except Exception as e:
                logger.warning(f"加载索引失败: {e}，自动重建")

        # 自动构建
        try:
            self._build_index()
            logger.info(f"FAISS 索引自动构建完成: {len(self.documents)} 条文档")
        except Exception as e:
            logger.error(f"FAISS 索引构建失败: {e}")
            self._offline = True
            self._loaded = False

    def _load_index(self):
        """从磁盘加载 FAISS 索引和元数据"""
        try:
            import faiss
            self.index = faiss.read_index(_INDEX_FILE)

            with open(_META_FILE, "rb") as f:
                self.documents = pickle.load(f)

            self._init_embedding()
            self._loaded = True
            self._offline = False
        except ImportError:
            logger.warning("faiss 未安装，无法加载索引")
            raise
        except Exception:
            raise

    def _build_index(self):
        """读取 data/knowledge 下的 txt 文件，构建 FAISS 索引并持久化"""
        self._init_embedding()

        # 读取所有知识文档
        docs = self._load_documents(_KNOWLEDGE_DIR)
        if not docs:
            logger.warning("未找到知识文档，知识库为空")
            self._offline = True
            return

        # 向量化
        texts = [d["content"] for d in docs]
        try:
            embeddings = self._embed_texts(texts)
        except Exception as e:
            logger.error(f"向量化失败: {e}")
            self._offline = True
            return

        # 构建 FAISS 索引
        import numpy as np
        try:
            import faiss
        except ImportError:
            logger.error("faiss 未安装，无法构建索引")
            self._offline = True
            return

        dim = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dim)
        self.index.add(embeddings.astype(np.float32))
        self.documents = docs

        # 持久化
        os.makedirs(self.index_path, exist_ok=True)
        faiss.write_index(self.index, _INDEX_FILE)
        with open(_META_FILE, "wb") as f:
            pickle.dump(self.documents, f)

        self._loaded = True
        self._offline = False

    def _init_embedding(self):
        """
        初始化 embedding 函数。
        优先使用 DeepSeek/豆包 API embedding，不可用时降级到本地 sentence-transformers。
        """
        if self.embedding_fn is not None:
            return

        # 尝试方法1：使用 OpenAI 兼容的 embedding（DeepSeek/豆包）
        try:
            from modules.ai.deepseek_client import deepseek_client
            # DeepSeek API 使用 openai 兼容接口
            client = deepseek_client.client

            def _remote_embed(texts: list[str]):
                resp = client.embeddings.create(
                    model="deepseek-embedding",  # DeepSeek 向量模型；豆包可改为对应 embedding 模型
                    input=texts,
                )
                import numpy as np
                return np.array([d.embedding for d in resp.data], dtype=np.float32)

            self.embedding_fn = _remote_embed
            logger.info("使用远程 Embedding API")
            return
        except Exception as e:
            logger.warning(f"远程 Embedding 不可用: {e}，尝试本地模型")

        # 尝试方法2：本地 sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

            def _local_embed(texts: list[str]):
                return model.encode(texts, convert_to_numpy=True).astype("float32")

            self.embedding_fn = _local_embed
            logger.info("使用本地 SentenceTransformer Embedding")
            return
        except Exception as e:
            logger.warning(f"本地 Embedding 不可用: {e}")

        # 方法3：最终降级 - TF-IDF 伪向量（不支持 FAISS，降级到关键词）
        self.embedding_fn = None
        logger.warning("无可用的 Embedding 方案，依赖关键词匹配")

    def _embed_texts(self, texts: list[str]):
        """将文本列表向量化"""
        if self.embedding_fn is None:
            raise RuntimeError("Embedding 函数不可用")
        return self.embedding_fn(texts)

    def _load_documents(self, directory: str) -> list[dict]:
        """
        从目录加载 txt 文档，每行作为一个段落。
        返回 [{"content": str, "source": str}, ...]
        """
        docs = []
        if not os.path.isdir(directory):
            return docs

        for filename in os.listdir(directory):
            if not filename.endswith(".txt"):
                continue
            filepath = os.path.join(directory, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                # 按段落分割（空行分隔）
                paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
                for p in paragraphs:
                    if len(p) > 10:  # 过滤太短的段落
                        docs.append({"content": p, "source": filename})
            except Exception as e:
                logger.warning(f"读取 {filename} 失败: {e}")

        logger.info(f"从 {directory} 加载了 {len(docs)} 条文档")
        return docs

    def _search(self, query: str, top_k: int) -> list[dict]:
        """
        FAISS 语义检索。
        返回 [{"content": str, "source": str, "score": float}, ...]
        """
        import numpy as np

        # 向量化查询
        query_vec = self.embedding_fn([query])
        if query_vec is None or len(query_vec) == 0:
            return []

        # 检索
        distances, indices = self.index.search(
            query_vec.astype(np.float32), min(top_k, len(self.documents))
        )

        results = []
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < 0 or idx >= len(self.documents):
                continue
            # L2 距离转相似度分数 (距离越小越相似)
            score = float(1.0 / (1.0 + dist))
            results.append({
                "content": self.documents[idx]["content"],
                "source": self.documents[idx]["source"],
                "score": round(score, 4),
            })

        return results

    def _keyword_match(self, query: str, top_k: int) -> list[dict]:
        """
        关键词匹配降级方案。
        在文档中匹配包含 query 关键词的段落。
        """
        results = []
        keywords = query.lower()

        for doc in self.documents:
            content_lower = doc["content"].lower()
            if keywords in content_lower:
                results.append({
                    "content": doc["content"],
                    "source": doc["source"],
                    "score": 0.5,  # 关键词匹配给固定中等分数
                })

        return results[:top_k]

    def _get_fallback_msg(self, query: str) -> str:
        """根据 query 关键词返回预设兜底回复"""
        for keyword, msg in self.FALLBACK_KNOWLEDGE.items():
            if keyword in query:
                return f"[离线兜底] {msg}"

        return (
            "抱歉，当前无法查询车辆知识库。请确保网络连接正常，"
            "或查阅车辆随车说明书。您也可以联系售后服务中心获取帮助。"
        )


# ── 全局单例 ──
_kb_instance: Optional[VehicleKnowledgeBase] = None


def get_knowledge_base() -> VehicleKnowledgeBase:
    """获取全局知识库单例"""
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = VehicleKnowledgeBase()
    return _kb_instance


def retrieve_knowledge(query: str, top_k: int = 3) -> dict:
    """快捷检索函数，供 interaction_agent 直接调用"""
    kb = get_knowledge_base()
    return kb.retrieve_knowledge(query, top_k)
