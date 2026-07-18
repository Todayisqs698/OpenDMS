# Agent modes
> Source: /documentation/working-in-code-banana/agent-mode

Understand the different agent modes and how to collaborate in your projects

## Project and Chat modes

Each project in CodeBanana has a corresponding group chat that supports three distinct chat modes for different collaboration needs.

### Chat modes

Every project group chat includes three modes:

#### Team agent

Team Agent mode is designed for **shared, controlled collaboration with AI** in a team environment. Instead of each individual interacting with a separate assistant, the team works with a **single, project-level agent** that operates on a shared codebase, shared context, and shared objectives.

This mode ensures that AI-driven changes remain **visible, coordinated, and aligned** across the entire team.

  ![Chatmodes](/images/chatmodes.png)

#### **What is Team Agent**

Team Agent is a **centralized AI collaborator** for the project:

- Operates on the **entire project context** (repo, files, discussions, history)
- Acts as a **shared execution layer** for coding, refactoring, debugging, and task automation
- Ensures all AI-generated changes are **transparent and traceable** within the team workspace

Unlike personal AI tools, Team Agent is not private. Every interaction contributes to the **collective project state**.

#### **Collaboration**

To maintain consistency and avoid conflicts, Team Agent follows a **controlled interaction model**:

- Only one team member can interact with the agent at a time. By default, interaction with the Team Agent is restricted to the **project owner**
- When other members want to use the Team Agent:
  - They must **request access from the owner**
  - Once approved, **only that member is granted interaction rights with the agent**
  - During this period, all other members do not have access until control is reassigned
- During an active session:
  - The agent executes tasks based on the current user’s instructions
  - All changes are **immediately visible to the team**
- Usage is attributed to the **project owner**

This model ensures that AI actions are **sequential, reviewable, and non-conflicting**, similar to a “single writer” system in collaborative editing.

  ![Teamagentrequest](/images/Teamagentrequest.png)

#### **Agent Modes**

Agent Modes define how the agent interacts with your project, from read-only assistance to direct code execution.

- **Ask-only** Read-only mode. The agent answers questions and provides guidance without modifying any files.
- **Coding** Execution mode. The agent can directly write and edit code within the project.
- **CodeBanana (CB Optimized Model)** Enhanced for project-level tasks with pre-installed capabilities such as deployment.
- **Claude Code (Claude Native Model)** Consistent with the native Claude experience. Requires more explicit prompting and user guidance.

  ![Agentmode](/images/Agentmode.png)

#### Private agent

Private Agent mode（My agent before） provides **personal AI assistance within the project**, allowing users to work independently without affecting the shared workflow.

**What is Private Agent**

A private, user-level agent that operates outside of the Team Agent.

It is designed for:

- Asking questions
- Planning tasks
- Exploring ideas All interactions are **isolated from the team’s active workflow**.
- **Usage Characteristics**
  - Primarily operates in **ask mode (read-only)**
  - Can be used **in parallel with Team Agent sessions**
  - Does not modify the shared project
  - Usage is **charged to** the project owner, not the **individual user**
  - Follows the user’s personal plan or usage-based billing

My Agent enables users to stay productive individually, while keeping the team-level collaboration **structured and conflict-free**.

  ![Myagent](/images/Myagent.png)

### **Discussion**

Discussion mode is a **team-wide communication space** designed for open collaboration without AI intervention.

**What is Discussion**

- A shared chat channel where team members can discuss ideas, align on requirements, and coordinate work.
- It serves as the **human layer of collaboration**, separate from agent-driven execution.

**Usage Characteristics**

- All members can **participate freely**
- Supports **real-time discussions, feedback, and decision-making**
- Conversations are visible to the entire team and remain part of the project context

**Agent Involvement**

- No agent is involved in this mode
- No code execution or automated actions are triggered

Discussion mode ensures teams have a dedicated space for **clear communication and alignment**, complementing the structured workflows of agent-based collaboration.

  ![Disscussion](/images/Disscussion.png)
