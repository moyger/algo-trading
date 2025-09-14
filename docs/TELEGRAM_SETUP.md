# Telegram Notification Setup Guide

## 📱 Create Telegram Bot

### 1. Create Bot
1. Search for `@BotFather` in Telegram
2. Send `/newbot` command
3. Follow prompts to set Bot name and username
4. Save the obtained `Bot Token` (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Get Chat ID

#### Method 1: Using Bot
1. Search and start conversation with your created Bot
2. Send any message to the Bot
3. Visit in browser: `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates`
   - Replace `<BOT_TOKEN>` with your actual Token
4. Find the `id` value in the `"chat":{"id":123456789}` part of the returned JSON

#### Method 2: Using @userinfobot
1. Search for `@userinfobot` and send `/start`
2. It will return your user information including the `Id` field

## 🔧 Configure Environment Variables

Add the following configuration in `.env` file:

```bash
# Telegram notification configuration
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789
ENABLE_NOTIFICATIONS=true
NOTIFICATION_INTERVAL=3600
```

### Configuration Description
- `TELEGRAM_BOT_TOKEN`: Bot Token obtained from BotFather
- `TELEGRAM_CHAT_ID`: Your Telegram user ID
- `ENABLE_NOTIFICATIONS`: Whether to enable notifications (true/false)
- `NOTIFICATION_INTERVAL`: Scheduled summary notification interval (seconds, default 3600=1 hour)

## 📋 Notification Types

### 🚨 Urgent Notifications (with sound alerts)
- **Position exceeds risk threshold**
- **Price spread deviation warning**
- **Configuration error**
- **WebSocket connection failure**
- **Runtime exception**

### 🔔 Important Notifications (with sound alerts)
- **Bot startup successful**
- **Inventory risk control (bidirectional position reduction)**
- **Grid price realignment**

### 🔇 Silent Notifications (no sound alerts)
- **Scheduled summary notifications** (every 1-4 hours)
  - Current position status
  - Pending order statistics
  - Account balance changes
  - Price information
  - Running status
- **Bot stop notification**

## 🎯 Notification Examples

### Startup Notification
```
🤖 X Grid Bot | 2024-01-15 10:30:00

🚀 Bot startup successful

📊 Trading configuration
• Symbol: X
• Grid spacing: 0.40%
• Initial quantity: 1 contract
• Leverage: 20x

🛡️ Risk control
• Lock position threshold: 30.00
• Position monitoring threshold: 15.00
• Price spread threshold: 0.0400%

✅ Bot has started running, will automatically perform grid trading...
```

### Risk Warning
```
🚨 Urgent Notification 🚨

🤖 X Grid Bot | 2024-01-15 14:30:00

⚠️ Position risk warning

📍 LONG position exceeds maximum threshold
• Current long position: 35 contracts
• Maximum threshold: 30.00
• Latest price: 0.62850000

🛑 New opening suspended, waiting for position to fall back
```

### Silent Summary Notification
```
🔇 Scheduled Summary 🔇

🤖 X Grid Bot | 2024-01-15 15:30:00

📊 Running status summary

💰 Account information
• USDT balance: 1250.35 (change: +15.20)

📈 Position status
• Long position: 12 contracts
• Short position: 8 contracts

📋 Order status
• Long opening: 1 contract
• Long take-profit: 1 contract
• Short opening: 1 contract
• Short take-profit: 1 contract

💹 Price information
• Latest price: 0.62850000
• Best bid: 0.62840000
• Best ask: 0.62860000

🏃‍♂️ Bot running normally...
```
*Note: This type of message will not produce sound alerts*

## 📊 Notification Overview

| Notification Type | Send Method | Sound Alert | Frequency/Trigger | Priority |
|------------------|-------------|-------------|-------------------|----------|
| 🚀 Startup notification | Event triggered | ✅ With sound | Once at startup | 🟢 Info |
| ⚠️ Position risk warning | Event triggered | ✅ With sound | When threshold exceeded | 🔴 Urgent |
| 📈 Price spread warning | Event triggered | ✅ With sound | Every 30 seconds check | 🔴 Urgent |
| 📉 Risk reduction notification | Event triggered | ✅ With sound | Both directions exceed threshold | 🟡 Important |
| ❌ Error/Exception notification | Event triggered | ✅ With sound | When exception occurs | 🔴 Urgent |
| 📊 Scheduled summary | Timed send | 🔇 Silent | Every 1-4 hours | 🔵 Regular |
| 🛑 Stop notification | Event triggered | 🔇 Silent | Manual stop | 🟢 Info |

### 🔧 Technical Implementation
- **With sound**: `disable_notification=false` (default)
- **Silent**: `disable_notification=true`
- **Urgent flag**: Add 🚨 icon and special formatting
- **Silent flag**: Add 🔇 icon

## 🛠️ Test Configuration

After starting the bot, if configured correctly, you should receive a startup notification. If you don't receive it:

1. Check if Bot Token and Chat ID are correct
2. Confirm you have sent a message to the Bot
3. Check logs for sending failure error messages

## 🔐 Security Tips

- **Do not** share your Bot Token in public places
- **Do not** commit Bot Token to code repository
- Regularly check Bot's message history
- If you find anomalies, promptly replace Bot Token 