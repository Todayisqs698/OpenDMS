# Team plan
> Source: /documentation/teams/teamplan

Designed for organizations that need shared resources, centralized billing, and controlled access across multiple members.

import SnippetIntro from '/snippets/snippet-intro.mdx';

## **What is Team Plan**

Team Plan provides a **collaborative usage model** where:

- Resources (requests, compute, usage limits) are managed at the **organization level**
- Billing is centralized under the **organization owner**

### **Plan Structure**

Team Plan consists of two main components:

**Prepaid (Included Usage)**

- Each member receives **300 requests per month**
- VM configurations can be selected based on usage needs, controlled by the **organization admin**
- Costs vary depending on the selected VM tier (charged as seat fees)

**Postpaid**

- Activated when included requests are exhausted
- Additional usage is billed based on actual consumption
- Usage limits are defined and controlled by the **organization admin**

## **Upgrade to Team Plan**

**_Admin Actions_**

### Step: Go to Pricing Page

    After logging in, the admin navigates to the **Pricing / Subscription** page and locates the **Team Plan**.

      ![Upgradetoteam](/images/upgradetoteam.png)

### Step: Click “Subscribe” and Complete Payment

    Click the **Subscribe** button to finish the payment process.

    - Upon activation, the system will immediately charge for the first seat (the admin’s own seat).

      ![Teampayment](/images/teampayment.png)

      By default, activating the Team Plan charges for one seat (the admin). Additional seats will be billed based on the actual number of members added later. Please ensure a valid credit card is linked and has sufficient balance.

## **Admin Controls**

Organization owners manage Team Plan configuration and billing:

#### **Add members to Team Plan**

### Step: Go to Usage

    Click the avatar in the top-right corner

    Select “Usage” from the dropdown to enter the usage management page

      ![Teamplanstep1](/images/Teamplanstep1.png)

### Step: Members & Quotas

    Switch to the “Members & Quotas” tab.

      ![Teamplanstep2](/images/Teamplanstep2.png)

### Step: Click 「Add Members」

    Click the blue “Add Members” button to open the member selection modal

      ![Teamplanstep3](/images/Teamplanstep3.png)

      ![Teamplanstep3](/images/addnewteam.png)

### Step: Select VM specifications and billing settings

    Enter the configuration step to assign VM specs for members

    Supports both bulk configuration and per-member customization

      ![Teamplanstep4](/images/Teamplanstep4.png)

  Seat fees are charged **IMMEDIATELY** to the **owner’s payment method** based on VM configuration

  Before adding members to the Team Plan, users must first request to join the admin’s organization. Only after the admin approves the request can seats be assigned.

#### **Modify member plans**

**Admins can update:**

- VM configuration
- On-demand usage limits
  - Members can only use resources within the configured limit
  - Usage beyond the limit will be blocked

  ![Addteamplanmember](/images/addteamplanmember.png)

  ![Chang Vm](/images/changVm.png)

**Upgrade behavior**:

- Takes effect immediately
- Price difference is charged to the owner（**VM Change Only）**

**Downgrade behavior**:

- Remaining balance is stored in Stripe（**VM Change Only**），used to offset future billing
- Refunds require manual request via email

**Remove member**:

- Team plan members can be removed by the admin
- Removed members cannot be re-added for a cooling period (7–30 days)
- Re-adding is only allowed after the cooling period ends

  ![Teamplanremove](/images/teamplanremove.png)

**Billing management**

- All invoices are available in **Personal Center → Billing**

  ![Teamplanbill](/images/teamplanbill.png)

#### **Pricing Logic of Upgrade/Downgrade**

Usage cost is calculated based on the **higher value of**:

- **(Total plan value / total days) × days used**, or
- **\$0.15 per request**

Remaining balance:

- Balance = Paid amount − Used amount
- Upgrade cost = New price − Remaining balance

#### **Member Experience**

After Team Plan is enabled:

Members must be **manually added by the admin**

Once added, they receive:

- 300 monthly requests
- Assigned VM resources
- Configured usage limits

If limits are reached:

- Members must contact the admin to increase quota

If a member is **not added to Team Plan**:

- Their usage is billed under their **personal plan**

#### **Billing Mechanism**

**Seat fees**

- The admin seat fee will be charged upon activating the Team Plan
- Charged to the owner when members are added

**Usage billing**

- Automatically charged when:
  - On-demand usage reaches **\$2000**, or
  - Every **30 days**

#### **Usage Tracking**

Go to **Personal Center → Usage** to view:

- Token consumption
- Request usage
- Overall quota and limits

  ![Teamplanusage](/images/teamplanusage.png)

## FAQs

Answers to common questions about Team Plan

### Why can’t I find a member in the “Add Members” list?

    The member has not completed the request to join the organization. Ask them to log in to CodeBanana, go to “Personal Center → Organization,” search for your organization, and submit a request. Once approved, they will appear in the addable list.

### Can different VM configurations be assigned to different members?

    Yes. In step of Add Members, the “Per-Member Configuration” section allows individual VM specs and usage limits to be set for each member.

### What happens when a member exceeds the usage limit?

    Once the On-Demand limit is exceeded, the member will no longer be able to use on-demand resources until the admin increases their limit.

### Is the 30-day billing cycle fixed or rolling?

    It follows a rolling 30-day cycle starting from the activation of the Team Plan, not a fixed monthly date. Billing will be triggered earlier if total usage reaches \$2,000.

### Where can I view billing records?

    Admins can view all billing history and per-member usage details on the Usage page. Billing notifications are also sent to the admin’s registered email.
