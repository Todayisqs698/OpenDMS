# Projects and Chats
> Source: /documentation/working-in-code-banana/project-and-chat

Communicate and collaborate with team members in CodeBanana

## **Projects**

Projects are the core unit of work, combining code, environment, and collaboration into a single workspace.

#### **Project List**

The project list provides flexible management and navigation:

**Filtering and sorting**:

- By project type, owner, creation time, last activity, etc.

**Project types and structure**:

- Visual indicators for:
  - GitHub projects
  - Local projects
- Projects from the same repository branch are **grouped under a single parent**

![Projectlist](/images/projectlist.png)

![Projectlist 1](/images/projectsort.png)

**Project operations**:

- Additional actions available via the “…” menu
- Permissions apply to all destructive actions

**File and folder management**:

- Folders: Rename, create, upload, copy path, move, delete, download
- Files: Rename, copy path, move, delete, download

**Relative path copy**:

- Copies the file path relative to the project or workspace root
- Deletion requires **agent-level permissions**

**Constraints**:

- Only the **project owner** can delete a project
- Deletion is allowed **only if the owner has more than one project**

    ![Operateproject](/images/operateproject.png)

#### **Create Project**

CodeBanana supports multiple ways to initialize a project

**Project sources**:

- Create a local project
- Import from GitHub or GitLab

**Templates**:

- Pre-configured templates based on use cases:
  - Include styles, skills, and agent settings
- Option to start from **Custom (empty project)**

  ![Studio Page](/images/StudioPage.png)

## **User Guide**

After creating a new project, a **User Guide** directory is automatically generated within the project file tree.

This directory contains detailed documentation for CodeBanana’s core features, including both English and Chinese versions. It covers the main modules in Studio and serves two purposes:

- As a **readable reference** for users to understand product capabilities
- As a **knowledge source** that agents can access during task execution

  ![Projectuserguide](/images/projectuserguide.png)

### **Adding Members**

**All members** in a project can expand the project team in two ways, depending on whether collaborators are part of your organization or external.

**Add organization members**

Add existing members from your organization directly into the project group chat without notification.

  ![Inviteorgnew](/images/inviteorgnew.png)

**Invite external contacts**

Bring external collaborators into the project using the **Invite external contacts** feature by email:

- Sent a notification and email to invite an external friends
- They do **not become members of your organization**
- Their access is limited to the project they are invited to

This is ideal for:

- Temporary collaborators
- Clients or stakeholders
- External partners who need visibility or participation without full organizational access

  ![Inviteexternalnew](/images/inviteexternalnew.png)

### **Member Management**

Project membership is managed by the **project owner**, who can access member management by clicking the icon in the top-right corner of the agent panel.

**Remove Members**

The **project owner** can remove members from the project group:

- Removed members will **lose access to the project and its chat**
- This action is typically used to:
  - Manage team changes
  - Revoke access for external collaborators

**Disband Group**

- The **project owner** can disband the entire project group:
  - All members will be **removed from the group chat**
  - The collaboration session is effectively **terminated**
  - This action is irreversible and should be used with caution

Only the **owner** has permission to perform these actions, ensuring that critical changes to team structure remain **controlled and secure**.

  ![Groupmanagement](/images/groupmanagement.png)

#### **Support Access**

Projects can request dedicated support:

- Use **Request Support** to bring in technical assistance
- A support member is automatically assigned to the project chat
- During support sessions: All token usage is billed at **1.5× rate**

  ![Supportaccess](/images/supportaccess.png)

## Chat

Chats provide a **dedicated space for human-to-human communication**, separate from agent-driven workflows. They are used for coordination, quick discussions, and cross-team collaboration.

You can start new chats in two ways:

- Click **New Chat** to create Group chats
- Go to **Personal Center → Contacts**, and select a member to start a direct conversation

  ![Chat](/images/chat.png)

  ![Contacts 1v1](/images/contacts-1v1.png)

#### **Messaging Features**

Chats support essential messaging capabilities for efficient communication:

- Copy, quote, and forward messages
- Automatic notifications when members join or leave a group
- Search across:
  - Organization contacts
  - Chat history

**Forwarding behavior**

- Messages can be forwarded to:
  - The current group
  - Other groups (must selected)
- Restrictions:
  - In **Team Agent**, messages can only be forwarded to destinations with agent access
  - In **My Agent** and **Discussion**, forwarding is unrestricted
- **Restore (agent-related)**
  - Available on user prompts in agent conversations
  - Allows reverting the conversation, model memory, and project state to a previous point
  - Not available in standard chat-only conversations

  ![Messageaction](/images/messageaction.png)

### **New Messages**

New messages help you quickly identify incoming activity across chats, projects, and notification, so you can stay aligned with your team in real time.

#### **Where New Messages Appear**

New message indicators are shown across key areas:

- **Chats**
- **Projects**
- **Notifications**

These indicators highlight where new interactions or updates have occurred.

#### **Priority Handling**

Not all messages are treated equally:

- **@mentions are prioritized** over general new messages
- Mentioned messages are surfaced first, helping you focus on what requires immediate attention

  ![Newmessage](/images/newmessage.png)

## Notification

Notifications keep you informed about important activities across your workspace, including permissions and collaboration events.

Notifications cover key events such as:

- Agent permission requests and approvals
- Organization join requests and status updates
- External project invitation
- Billing and usage updates (reach limited)
- Group invitation

All notifications are centralized in the **Notifications panel**, where you can:

- Track actions that require your attention
- Quickly navigate to related projects or contexts

  ![Notification](/images/notification.png)
