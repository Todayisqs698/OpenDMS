# Dev Tools
> Source: /documentation/working-in-code-banana/dev-tools

Dev Tools are accessible from the bottom-left panel and include Terminal, Service, and Git Status.

### **Terminal**

The built-in Terminal allows developers to interact directly with the project environment.

- Execute commands within the project’s runtime environment
- Useful for:
  - Installing dependencies
  - Running scripts
  - Debugging issues
- Designed to support more advanced or custom development workflows

  ![Devtool](/images/devtool.png)

### **Service**

The Service panel manages runtime processes and active ports.

- View all **active services and ports**
- Restart the VM environment if a service fails
- Kill specific processes or ports when needed

This helps ensure your application runs smoothly and can be quickly recovered if issues occur.

  ![Service](/images/service.png)

### **Git Status**

Git Status provides version control visibility and basic operations.

- View current file changes
- Create commits using the **Save** action
- Access commit history:
  - Review previous versions
  - Restore to a specific commit if needed

This allows teams to track changes and maintain a clear development history directly within the workspace.

  ![Gitoverview](/images/gitoverview.png)

  ![Gitnew](/images/gitnew.png)

### **Deploy**

Deploy enables you to publish your project as a **persistent, shareable link**:

- Generates a stable URL that does not expire
- Automatically updates when the project changes
- Best suited for:
  - Static websites
  - Lightweight applications

It is recommended to verify your project using preview before deploying.
