# Project Viewer
> Source: /documentation/working-in-code-banana/projectViewer

The Project Viewer is the central workspace where you interact with files, preview outputs, and inspect changes in real time.

## **File Navigation and Tabs**

When working within a project, opened files are organized into tabs for easy switching:

- Multiple files can be opened simultaneously
- Tabs appear at the top of the viewer
- Right-click on tabs to:
  - Close current
  - Close others
  - Close all

This allows you to manage context efficiently while working across different parts of the project.

  ![Viewertab](/images/viewertab.png)

## **File View and Preview**

The viewer supports both **code and preview modes**, depending on file type:

**Markdown (md)**

- Switch between **Code** and **Preview**
- Edit directly in preview mode
- Use / to trigger formatting options
- Select a line and **right-click for formatting and editing actions**

  ![Mdedit](/images/mdedit.png)

  ![Markdownpreview](/images/markdownpreview.png)

**HTML / JSON / static files**

- Code view and preview mode available
- Option to open in a new tab

  ![Htmlpreview](/images/htmlpreview.png)

**App projects**

- Preview across multiple environments:
  - Web
  - iOS
  - Android
  - My Device (via external preview tools)
- Refresh available for real-time updates

## **Project Preview**

When a service is running, the Project Viewer enables **live preview**:

- Automatically detects active ports
- Allows instant access to running applications
- Can also be accessed via the **Service panel**

This creates a “what you see is what you build” experience, similar to real-time document editing—but for applications.

  ![Projectpreview](/images/projectpreview.png)

## **Editing and Interaction**

The Project Viewer supports direct interaction with project content:

- Select content to:
  - Add comments
  - Reference in chat
  - Copy content
- Comments are tied to specific lines and remain visible in context
- A floating comment panel allows quick navigation across all comments

  ![Comment](/images/comment.png)

## **Diff and Change Tracking**

When files are modified, additional views are available:

- **Preview** — current state of the file
- **Diff View** — compare changes against previous versions

This helps teams understand exactly what has changed before committing or sharing updates.

  ![Diff](/images/diff.png)

## **Sharing**

Certain file types (e.g. HTML, Markdown, JSON) support **shareable links**, allowing others to view content externally without accessing the full project.

  ![Share](/images/share.png)

  ![Shareexam](/images/shareexam.png)
