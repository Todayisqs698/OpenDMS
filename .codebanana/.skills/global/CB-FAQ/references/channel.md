# Channel (IM Settings)
> Source: /guides/working-in-code-banana/imsetting

## **What is Channel**

Channel is a bridge between CodeBanana and external IM tools.

By configuring a bot, you can send messages from platforms like Slack or Telegram directly to your project agent and receive responses in return.

This enables a more flexible workflow where the agent is accessible **across different communication environments**.

#### **Supported Platforms**

You can connect the agent to multiple IM platforms, including:

- Feishu
- Telegram
- Slack
- Discord
- DingTalk
- WeCom
- QQ
- Mattermost

  ![Channel](/images/channel.png)

### **Create a Bot**

To enable Channel, you need to create and configure a bot:

- Go to **Agent Config → Channel → Add Bot**
- Select the target IM platform
- Provide required credentials (e.g. ID and Secret)
- Once configured correctly:
  - Status shows as **Connected**
  - Invalid configurations will show as **Disconnected**

You can create multiple bots for the same platform if needed.

  ![Channelexam](/images/channelexam.png)

  ![Bindabot](/images/bindabot.png)

#### **Bind Bot to Project**

After creating a bot, it must be linked to a specific project:

- Select a bot and **bind it to the project**
- Each project can bind **only one bot**
- Each bot can be bound to **only one project**

Only bots in **Connected** status can be bound.

  ![Bindbot](/images/bindbot.png)

## **How It Works**

Once connected:

- Messages sent from the external platform are routed to the project Team Agent
- The agent processes the request using the same project context
- Responses are returned to the external platform

This allows teams to interact with the agent **without entering the CodeBanana interface**.