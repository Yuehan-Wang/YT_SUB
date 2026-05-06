import os
import json
import feedparser
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import google.generativeai as genai

# ================= 配置区 =================
CHANNEL_ID = "UCFhJ8ZFg9W4kLwFTBBNIjOw"  # NaNa说美股 的频道 ID
RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
STATE_FILE = "last_video.json"
MY_STOCKS = "苹果(AAPL), 特斯拉(TSLA), 英伟达(NVDA), 微软(MSFT)"
# ==========================================

def get_latest_video():
    """获取最新视频信息"""
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        return None, None
    latest = feed.entries[0]
    return latest.yt_videoid, latest.title

def get_transcript(video_id):
    """通过 RapidAPI (youtube-transcriptor) 获取字幕"""
    try:
        url = "https://youtube-transcriptor.p.rapidapi.com/transcript"
        
        querystring = {"video_id": video_id} 

        headers = {
            "x-rapidapi-key": os.environ["RAPIDAPI_KEY"],
            "x-rapidapi-host": "youtube-transcriptor.p.rapidapi.com"
        }

        response = requests.get(url, headers=headers, params=querystring)
        response.raise_for_status() 
        data = response.json()
        
        # 【核心保护机制】：拦截 API 返回的无字幕错误
        if isinstance(data, dict) and "error" in data:
            error_msg = data["error"].lower()
            if "no subtitles" in error_msg or "not found" in error_msg:
                 print(f"API 明确返回无字幕错误: {data['error']}")
                 return None

        # 提取正常字幕文本的逻辑
        if isinstance(data, list):
            return " ".join([item.get('text', '') for item in data if 'text' in item])
        elif isinstance(data, dict):
            if "transcript" in data:
                return " ".join([item.get('text', '') for item in data['transcript']])
            return str(data) 
        else:
            return str(data) 

    except requests.exceptions.HTTPError as e:
        print(f"HTTP 错误: {e}")
        print(f"API 服务器返回的详细错误信息: {e.response.text}")
        return None
    except Exception as e:
        print(f"通过 RapidAPI 获取字幕失败: {e}")
        return None

def summarize_with_gemini(text, title):
    """使用 Gemini 2.5 Flash 生成总结"""
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    
    # 使用最新的模型
    model = genai.GenerativeModel('gemini-2.5-flash') 
    
    prompt = f"""
    你是一个专业的美股财经助理。以下是 YouTube 财经博主最新视频的完整字幕内容。
    视频标题：{title}
    
    请帮我用中文总结出以下两部分内容，格式要求清晰、易读（使用 Markdown 排版），适合用邮件阅读：
    
    1. 【大盘总结】：博主对今天宏观经济、美股三大指数的走势分析和未来预期。提取核心观点和关键点位。
    2. 【我的关注个股】：我关心的股票是：{MY_STOCKS}。请仔细在字幕中寻找博主是否提到了这几只股票。如果提到了，请详细总结他对这些股票的支撑位、阻力位、财报分析或操作建议；如果完全没提到，请直接说明“今日未提及”。
    
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
    print("开始检查频道更新...")
    video_id, title = get_latest_video()
    
    if not video_id:
        print("未获取到视频信息。")
        return

    last_video_id = None
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            last_video_id = data.get("video_id")

    if video_id == last_video_id:
        print(f"视频 {video_id} 已经处理过，任务结束。")
        return

    print(f"发现新视频：{title} (ID: {video_id})")
    
    print("正在获取字幕...")
    transcript = get_transcript(video_id)
    if not transcript:
        print("无法获取字幕，流程终止。不更新记录，留待下次重试。")
        return

    print("正在请求 AI 总结...")
    summary = summarize_with_gemini(transcript, title)
    
    if not summary:
        print("AI 总结失败，流程终止。不更新记录，留待下次重试。")
        return

    print("正在发送邮件...")
    email_subject = f"【NaNa说美股 更新】{title}"
    send_email(email_subject, summary)
    print("邮件发送成功！")

    # 只有当发完邮件后，才真正把视频 ID 写入记录
    with open(STATE_FILE, "w") as f:
        json.dump({"video_id": video_id, "title": title}, f)
    print("状态已更新。")

if __name__ == "__main__":
    main()