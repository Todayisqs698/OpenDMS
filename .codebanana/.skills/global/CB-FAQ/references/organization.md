# Organization
> Source: /documentation/teams/org

Organization is the core collaboration unit in CodeBanana. It defines how users, projects, permissions, and billing are structured and managed

import SnippetIntro from '/snippets/snippet-intro.mdx';

import OrganizationManagement from '/snippets/Organization-Management.mdx';

### **Access and Switching**

Click the **organization selector in the top-left corner** to:

- Switch between organizations
- Apply to join a new organization

To **join** an organization:

- Search for the organization name
- Submit a request
- After approval by the **organization owner**, you can switch into that organization

  ![Switchorga](/images/switchorga.png)

#### **Create Organization**

- A default organization is **automatically created** when you register (via email or third-party login)
- The organization name is initially based on your email and can be renamed by the owner
- Each user can have **only one owned organization**

#### **Organization Types**

CodeBanana distinguishes between two types of organizations:

**Own Organization**

- The organization you created and fully control
- You are the **Owner**
- Each user can have only one

**Work Organization**

- Organizations you join as a collaborator
- You can be part of multiple work organizations

#### **Key behavior**

- You can only be in **one organization at a time**
- Switching organizations means switching your entire workspace:
  - Projects
  - Files
  - Contacts

#### **Members and Roles**

Organizations manage collaboration through roles:

- **Owner**
  - Full control over the organization
  - Manages members, permissions, and billing
- **Member**
  - Can access AI resources and participate in projects

#### **Join mechanism**

- Users must **actively apply** to join an organization
- Search by organization name and submit a request
- Access is granted after admin approval

  ![Joinorg](/images/joinorg.png)

#### **Leaving an organization**

- Users can switch between organizations if they belong to multiple
- Full removal currently requires action from the **organization owner**
- Self-service “leave organization” is not yet available (to prevent accidental data loss)

#### **Organization & Projects**

Projects are tightly bound to organizations:

**Strong binding**

- Every project must belong to a specific organization
- Projects cannot exist outside an organization

**Data isolation**

- Projects in one organization are **not visible** to members of another
- Switching organizations refreshes your entire project list

**External collaboration (special case)**

- If an external user is invited to a project:
  - They gain access to the **project only**, not the organization
  - Currently, the project may appear across their organization views
  - Future updates will place such projects under the user’s personal organization

### Organization Management

**Admin and owner** can manage the organization structure and members through **Contacts page**.

#### **Overview**

The Contacts module serves as the central place for:

- Organization structure management
- Member management and permissions
- Bulk operations for scaling teams

  ![Org Contacts](/images/org-contacts.png)

#### **Invitations**

Members can be added in two ways:

- **Invite Members (Manual)**

### Step: Open Contacts page

    - Click avatar  → contacts

      ![Clickavatar](/images/clickavatar.png)

### Step: Click invite members

    - Invite users individually via the **Invite Members** button

      ![Clickinvitebotton](/images/clickinvitebotton.png)

    - Enter the email address and select a department

      ![Individualinvite](/images/individualinvite.png)

- **Batch Import**

### Step: Open Contacts page

    - Click avatar  → contacts

      ![Clickavatar](/images/clickavatar.png)

### Step: Click the Top-right icon

      ![Toprighticon](/images/toprighticon.png)

    - Click Batch Import

### Step: Download template & Edit

    - Download two templates
    - Edit these templates under guidance

      ![Download Template](/images/downloadTemplate.png)

### Step: Upload template and preview

#### **Export files**

Exported files can be edited and re-uploaded:

- **Export Structure** — export department hierarchy
- **Export Members** — export member list

#### **Department Management**

**Admins and owner** can manage organizational structure:

- Create top-departments
- Add sub-departments under existing ones (**Add Sub-dept**)
- Edit department information

  ![Departmentmanage](/images/departmentmanage.png)

- Delete departments
- Update member name, role, and assigned department

  ![Editmemberifo](/images/editmemberifo.png)

- Remove Member
  - Requires transferring all projects owned by the member to another user
  - All organization permissions are revoked immediately upon removal

  ![Removemember](/images/removemember.png)
