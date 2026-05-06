import os
import json
import feedparser
import smtplib
import requests
import time
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai

# ================= 配置区 =================
CHANNEL_ID = "UCFhJ8ZFg9W4kLwFTBBNIjOw" 
RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
STATE_FILE = "last_video.json" 
MY_STOCKS = "苹果(AAPL), 特斯拉(TSLA), 英伟达(NVDA), 微软(MSFT)"
# ==========================================

def get_recent_videos():
    feed = feedparser.parse(RSS_URL)
    recent_videos = []
    now = datetime.now(timezone.utc)
    
    for entry in feed.entries:
        pub_time = datetime.fromtimestamp(time.mktime(entry.published_parsed), timezone.utc)
        
        if now - pub_time <= timedelta(hours=3):
            recent_videos.append((entry.yt_videoid, entry.title))
            
    return recent_videos[::-1]

def get_transcript(video_id):
    """通过新的 RapidAPI (youtube-transcripts) 获取字幕"""
    try:
        url = "https://youtube-transcripts.p.rapidapi.com/youtube/transcript"
        
        querystring = {"videoId": video_id, "text": "false"} 

        headers = {
            "x-rapidapi-key": os.environ["RAPIDAPI_KEY"],
            "x-rapidapi-host": "youtube-transcripts.p.rapidapi.com"
        }

        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status() 
        data = response.json()
        
        if isinstance(data, dict) and "error" in data:
            error_msg = data["error"].lower()
            if "no subtitles" in error_msg or "not found" in error_msg:
                 print(f"API 明确返回无字幕错误: {data['error']}")
                 return None

        if isinstance(data, list):
            extracted = " ".join([item.get('text', '') for item in data if isinstance(item, dict) and 'text' in item])
            if extracted.strip(): return extracted
            
        elif isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, list):
                    extracted = " ".join([item.get('text', '') for item in value if isinstance(item, dict) and 'text' in item])
                    if extracted.strip(): return extracted
            
            if "text" in data and isinstance(data["text"], str):
                return data["text"]

        print("警告：无法精确提取 text 字段，已将原始 JSON 传给 AI。")
        return str(data)

    except requests.exceptions.HTTPError as e:
        print(f"HTTP 错误: {e}")
        print(f"详细报错信息: {e.response.text}")
        return None
    except Exception as e:
        print(f"获取字幕失败: {e}")
        return None

def summarize_with_gemini(text, title):
    """使用 Gemini 2.5 Flash 生成总结"""
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash') 
    
    prompt = f"""
    你是一个专业的美股财经助理。以下是 YouTube 财经博主最新视频的完整字幕内容。
    视频标题：{title}
    
    请帮我用中文总结出以下两部分内容，格式要求清晰、易读（使用 Markdown 排版）：
    1. 【大盘总结】：宏观经济、美股三大指数走势分析和未来预期。
    2. 【我的关注个股】：{MY_STOCKS}。寻找博主对这些股票的支撑位、阻力位或操作建议；若未提及请说明。
    
    以下是视频字幕原文：
    {text}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"AI 生成总结失败: {e}")
        return None 

def send_email(subject, content):
    """发送邮件"""
    sender = os.environ["EMAIL_USER"]
    password = os.environ["EMAIL_PASS"]
    receiver = os.environ["EMAIL_RECEIVER"]

    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver
    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())

def main():
    print("开始检查过去 3小时内的视频...")
    videos = get_recent_videos()
    
    if not videos:
        print("过去 3小时内的视频。")
        return

    processed_history = []
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                processed_history = data.get("history", [])
        except:
            pass

    for video_id, title in videos:
        print(f"\n--- 正在处理: {title} ({video_id}) ---")
        
        if video_id in processed_history:
            print("该视频已经处理过，跳过。")
            continue
            
        print("正在获取字幕...")
        transcript = get_transcript(video_id)
        if not transcript:
            print("无法获取字幕，跳过当前视频，留待下次重试。")
            continue 

        print("正在请求 AI 总结...")
        summary = summarize_with_gemini(transcript, title)
        if not summary:
            print("AI 总结失败，跳过当前视频，留待下次重试。")
            continue

        print("正在发送邮件...")
        email_subject = f"【NaNa说美股】{title}"
        send_email(email_subject, summary)
        print("邮件发送成功！")

        processed_history.append(video_id)

    with open(STATE_FILE, "w") as f:
        json.dump({"history": processed_history[-20:]}, f)
    print("\n所有任务执行完毕，状态已更新。")

if __name__ == "__main__":
    main()