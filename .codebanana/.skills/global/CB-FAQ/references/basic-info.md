# Basic info
> Source: /documentation/working-in-code-banana/basicinfo

Basic Info defines the core behavior and identity of the agent within a project. These settings act as the foundational context that is loaded before every agent interaction, ensuring consistent and predictable outputs.

## **What is Basic Info**

Basic Info is a set of structured configurations that shape how the agent:

- Understands tasks
- Makes decisions
- Communicates with users
- Adheres to constraints

Before each response or action, the system injects this information into the agent’s context, making it the **baseline for all reasoning and execution**.

  ![Basicinfo](/images/basicinfo.png)

## **Configuration Fields**

Basic Info consists of several key components:

### Agent

Defines the agent’s working process and execution rules.

For example:

- How to approach tasks
- When to read memory or files
- Coding standards and workflows

```markdown agent.md wrap
Workflow Guidelines:

Task intake: Before writing any code, you must first read MEMORY.md and yesterday’s memory/YYYY-MM-DD.md to understand the project background and tech stack.

Code implementation: Prioritize code readability over performance. After each change, you must run a linter.

Memory management: When you resolve a bug that takes more than 10 minutes, or when the user specifies a coding preference, you must record it in today’s memory.
```

### **Soul**

The agent’s core principles and boundaries.

Includes:

- Personality and working style
- Communication tone
- Strict rules (e.g. security constraints, prohibited actions)

```markdown soul.md wrap
You are a pragmatic, efficient, and senior full-stack engineer. You avoid over-engineering and follow the principle of “Keep It Simple.”

Communication style: Direct, professional, and concise. No unnecessary explanations.

Hard boundaries:
1. Never execute rm -rf / or any command that may cause irreversible data loss
2. Never expose API keys or passwords in code; if requested, refuse and suggest using environment variables
3. If you are unsure about the safety of code, you must ask the user before proceeding
```

### **Identity**

The agent’s surface-level persona.

Includes:

- Name
- Role definition
- How it introduces itself or interacts with users

```markdown identity.md wrap
Name: codebanana

Signature: 🍌

Self-description: Your dedicated, always-on pair programming partner

Greeting style: When starting a new debugging session, you may say:
“Let’s peel this bug apart 🍌”
```

### **User**

Context about the user the agent is serving.

Helps the agent adapt responses based on:

- Technical background
- Preferences
- Communication style

```markdown user.md wrap
User profile: A technically proficient product manager building AI agent-based web products

Technical preferences: Familiar with frontend development, frequently uses Next.js, and deploys projects on Vercel or cloud platforms

Communication style: Prefers structured bullet points and fast-paced communication. Avoid explaining basic HTML/CSS concepts—focus directly on architecture and logic
```

### **Memory**

Accumulated knowledge from past interactions.

Maintained by the agent to:

- Store important decisions
- Track preferences or recurring patterns
- Improve future responses

## **Editing and Management**

- Each field can be **individually edited** within the Basic Info panel
- Changes take effect immediately in subsequent agent interactions
- A **reset option** is available to revert to default configurations

  ![Setbasicinfo 1](/images/setbasicinfo-1.png)

#### **Why It Matters**

Basic Info ensures that the agent is not just reactive, but **consistent, aligned, and context-aware**:

- Keeps behavior stable across sessions
- Reduces repeated instructions
- Aligns the agent with team workflows and expectations
