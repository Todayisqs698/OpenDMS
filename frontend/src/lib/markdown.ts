import { marked } from 'marked'

marked.setOptions({
  breaks: true,
  gfm: true,
})

const renderer = {
  link({ href, title, text }: { href: string; title: string | null; text: string }) {
    const titleAttr = title ? ` title="${title}"` : ''
    return `<a href="${href}"${titleAttr} target="_blank" rel="noopener noreferrer">${text}</a>`
  },
}
marked.use({ renderer })

export function renderMarkdown(text: string | undefined | null): string {
  if (!text || !text.trim()) return ''
  try {
    return marked.parse(text) as string
  } catch {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br>')
  }
}
