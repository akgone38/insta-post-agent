# 🏕️ Social Media AI Agent — State Park RV Village

An AI-powered social media posting agent designed to help **State Park RV Village** (Lockhart, TX) grow its organic following. Send a **photo or video** to the Telegram bot, and it will analyze the media using AI (extracting a preview frame for video files), write an engaging brand-aligned caption, and publish it concurrently to **Instagram** (as a Post or Reel) and **Facebook Page** (as a Photo or Video).

---

## 🤖 How It Works

### 1. System Architecture (Block Diagram)
```mermaid
graph LR
    subgraph Telegram Client
        U[📱 User] <--> Bot[🤖 Telegram Bot]
    end
    subgraph FastAPI Backend Server
        API[⚡ FastAPI Endpoints]
        Static[📁 Static File Server]
        TG_Handlers[🐍 Bot Message Handlers]
        Frame_Extractor[🖼️ OpenCV Frame Extractor]
        AI_Module[🤖 Llama Vision Client]
        FB_Module[📘 FB Page Publisher]
        IG_Module[📸 IG Business Publisher]
        
        API --> TG_Handlers
        TG_Handlers --> Frame_Extractor
        TG_Handlers --> AI_Module
        TG_Handlers --> FB_Module
        TG_Handlers --> IG_Module
        TG_Handlers --> Static
        Frame_Extractor --> AI_Module
    end
    subgraph External APIs
        HF[🤗 Hugging Face Serverless API]
        Meta_API[📸 Meta Graph APIs]
    end
    
    Bot <-->|Webhooks & Actions| API
    AI_Module <-->|Image analysis & Caption prompt| HF
    FB_Module -->|Post photo/video| Meta_API
    IG_Module -->|Post photo/video| Meta_API
```

### 2. Detailed Data Flow (Sequence Diagram)
```mermaid
sequenceDiagram
    autonumber
    actor User as 📱 User (Telegram)
    participant Telegram as 💬 Telegram API
    participant FastAPI as ⚡ FastAPI Server (Local/Cloud)
    participant HF as 🤗 Hugging Face Router API<br/>(Llama 3.2 Vision)
    participant FB as 📘 Meta Graph API<br/>(Facebook Page)
    participant IG as 📸 Meta Graph API<br/>(Instagram Business)

    User->>Telegram: Send Photo & optional Context Note
    Telegram->>FastAPI: POST /webhook/telegram (JSON update payload)
    activate FastAPI
    
    # Step 1: Download
    FastAPI->>Telegram: Download media file (bot.get_file)
    Telegram-->>FastAPI: Return file bytes
    FastAPI->>FastAPI: Save file to local disk (temp_images/)
    
    # Step 2: AI Caption
    Note over FastAPI, HF: 🤖 AI Caption Generation
    alt Media is Video
        FastAPI->>FastAPI: OpenCV: Extract first frame (temp JPG)
    end
    FastAPI->>FastAPI: Read image & convert to Base64 Data URI
    FastAPI->>HF: POST /v1/chat/completions (Image base64 + System Prompt)
    HF-->>FastAPI: Returns generated caption & hashtags
    alt Media is Video
        FastAPI->>FastAPI: Delete temporary extracted JPG frame
    end
    
    # Step 3: Facebook Post
    Note over FastAPI, FB: 📢 Publishing to Facebook Page
    alt Media is Video
        FastAPI->>FB: POST /v22.0/{page_id}/videos (file_url, description, Token)
    else Media is Photo
        FastAPI->>FB: POST /v22.0/{page_id}/photos (url, caption, Token)
    end
    FB-->>FastAPI: Returns FB post ID & permalink
    
    # Step 4: Instagram Post
    Note over FastAPI, IG: 📸 Publishing to Instagram
    alt Media is Video
        FastAPI->>IG: POST /v22.0/{ig_id}/media (media_type=REELS, video_url, Token)
    else Media is Photo
        FastAPI->>IG: POST /v22.0/{ig_id}/media (image_url, caption, Token)
    end
    IG-->>FastAPI: Returns Media Container ID
    
    loop Polling Status
        FastAPI->>IG: GET /v22.0/{container_id} (Check processing status)
        IG-->>FastAPI: Returns status (FINISHED / IN_PROGRESS)
    end
    
    FastAPI->>IG: POST /v22.0/{ig_id}/media_publish (Container ID)
    IG-->>FastAPI: Returns IG post ID & permalink

    # Step 5: Telegram Reply
    FastAPI->>Telegram: Send Success / Error Report message
    deactivate FastAPI
    Telegram->>User: Deliver Markdown message with post links!
```

---

## 🛠️ Prerequisites & Setup

You will need access tokens for three platforms: Telegram, Hugging Face, and Meta (Facebook/Instagram).

### 1. Telegram Bot Token
1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Use the `/newbot` command to create a new bot.
3. Save the **HTTP API Token** generated.

### 2. Hugging Face Token (AI Caption Model)
1. Register/Log in to [Hugging Face](https://huggingface.co/).
2. Go to **Settings** -> **Access Tokens** -> **Create New Token** (read permission is sufficient).
3. Save the token (starts with `hf_...`).

### 3. Meta Credentials (Instagram & Facebook)
1. **Instagram Business Account**: Ensure your Instagram account is switched to a **Business/Professional** account and linked to a **Facebook Page**.
2. **Meta Developer App**:
   - Create an app on the [Meta Developer Portal](https://developers.facebook.com/apps/).
   - Under **Use cases**, add **Manage messaging & content on Instagram** and **Manage everything on your Page**.
   - Customize the Page use case to add `pages_manage_posts`, `pages_read_engagement`, and `pages_show_list` permissions.
3. **Generate Page Access Token & ID**:
   - Open the **Graph API Explorer** tool.
   - Select your Facebook Page in the **User or Page** dropdown.
   - Grant permissions and generate the Access Token (starts with `EAA...`).
   - Copy the Page ID and Page Access Token.
4. **Get Instagram Account ID**:
   - Query `GET /me/accounts?fields=instagram_business_account` inside the Explorer to retrieve the connected Instagram Business account ID.

---

## 🚀 Local Development

### 1. Installation
Clone the repository, create a virtual environment, and install dependencies:
```bash
git init
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

Ensure `.env` contains:
```env
TELEGRAM_BOT_TOKEN="your-telegram-token"
HUGGINGFACE_API_TOKEN="your-huggingface-token"
INSTAGRAM_ACCOUNT_ID="your-instagram-account-id"
INSTAGRAM_ACCESS_TOKEN="your-instagram-access-token"
FACEBOOK_PAGE_ID="your-facebook-page-id"
FACEBOOK_PAGE_ACCESS_TOKEN="your-facebook-page-access-token"
WEBHOOK_BASE_URL="https://your-ngrok-url.ngrok-free.app"
```

### 3. Run ngrok (Local tunnel)
Since Meta and Telegram APIs communicate via webhooks, they must be able to reach your local server. Run ngrok to tunnel port 8000:
```bash
ngrok http 8000
```
Copy the `https://...` forwarding address and update `WEBHOOK_BASE_URL` in `.env`.

### 4. Start the Application
```bash
python main.py
```
On startup, the application will automatically register the webhook URL with Telegram. You will see:
```
✅ Telegram webhook set successfully
🚀 Server is ready! Waiting for photos on Telegram...
```

---

## 📱 Usage Guide
1. Go to your Telegram bot chat and press `/start`.
2. Send a **photo or video**. You can add a text caption along with the file to provide **custom context** (e.g., *"Check out our newly installed modern hookups on site #14!"*).
3. The bot will:
   - Download the photo or video.
   - For video files: extract the first frame using OpenCV.
   - Run multimodal image-to-text analysis using the **Qwen 3 VL / Llama 3.2 Vision** model on Hugging Face.
   - Generate a professional RV park marketing caption tailored to Lockhart, TX, complete with CTAs, emojis, and hashtags.
   - Post it concurrently:
     - **For Photos**: Published to your Facebook Page feed and Instagram Feed.
     - **For Videos**: Published as a Facebook Page Video post and an Instagram Reel.
   - Reply to you in Telegram with links to view both live posts.

---

## ☁️ Live Cloud Deployment (Railway / Render)
To make your agent run 24/7 without needing your laptop active:

1. **Deploy to Render or Railway**:
   - Push your code to a private GitHub repository.
   - Create a new web service on Railway or Render pointing to the repository.
   - Command to run: `uvicorn main:app --host 0.0.0.0 --port $PORT` (or just `python main.py`).
2. **Configure Environment Variables**:
   - Copy all variables from `.env` to the host's environment settings.
   - Set `WEBHOOK_BASE_URL` to the public domain given to you by the hosting provider (e.g., `https://statepark-rv-bot.up.railway.app`).

*Note: Ephemeral file storage on cloud platforms is perfectly fine. The image is downloaded to `temp_images/` only long enough for Instagram and Facebook to scrape it into their permanent CDNs, which happens instantly when the publish endpoints are triggered.*

---

## 🔑 Generating a Never-Expiring Facebook Page Token

By default, Facebook tokens generated inside the Graph API Explorer expire after 1–2 hours. To generate a **Never-Expiring Page Token** for your bot, follow these steps:

### Step 1: Get a Short-Lived User Access Token
1. Go to the [Graph API Explorer](https://developers.facebook.com/tools/explorer/).
2. Select your Meta App in the top right.
3. Under **User or Page**, select **Get User Access Token**.
4. Add permissions: `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`.
5. Click **Generate Access Token** and complete the popup checkmarks.

### Step 2: Exchange it for a Long-Lived User Token (60 Days)
1. Go to the [Access Token Tool / Debugger](https://developers.facebook.com/tools/accesstoken/).
2. Find the token you just created and click **Debug** on the right.
3. Scroll to the bottom of the details and click the blue **Extend Access Token** button.
4. Copy the newly generated **60-Day User Access Token**.

### Step 3: Extract the Never-Expiring Page Access Token
1. Open a new tab and run this request (replace with your Page ID and the 60-day User Token):
   ```
   https://graph.facebook.com/v22.0/{your-facebook-page-id}?fields=access_token&access_token={your-60-day-user-token}
   ```
2. The JSON response will return your **Never-Expiring Page Access Token**:
   ```json
   {
     "access_token": "EAATC3dJ...",
     "id": "1277749535419892"
   }
   ```
   *Note: Because this Page Token is generated using a long-lived User Token, Meta assigns it an infinite expiration time. It will remain valid forever unless you change your Facebook password or uninstall the app.*

