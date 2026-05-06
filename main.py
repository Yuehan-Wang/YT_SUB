import os
import json
import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai

CHANNEL_ID = "UCFQsi7WaF5X41tcuOryDk8w"  # RhinoFinance的频道ID
RSS_URL = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
STATE_FILE = "last_video.json"

MY_STOCKS = "英伟达(NVDA), 微软(MSFT), 谷歌(GOOGL)"  

def get_latest_video():
    """获取最新视频信息"""
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        return None, None
    latest = feed.entries[0]
    return latest.yt_videoid, latest.title

def get_transcript(video_id):
    """获取视频中文字幕"""
    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.fetch(video_id, languages=['zh-Hans', 'zh-Hant', 'en'])
        text = " ".join([t['text'] for t in transcript_list])
        return text
    except Exception as e:
        print(f"字幕获取失败: {e}")
        return None

def summarize_with_gemini(text, title):
    """使用 Gemini 生成总结"""
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash') 
    
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
        return "AI 总结生成失败，请检查 API 或日志。"

def send_email(subject, content):
    """发送邮件"""
    sender = os.environ["EMAIL_USER"]
    password = os.environ["EMAIL_PASS"]
    receiver = os.environ["EMAIL_RECEIVER"]

    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver

    # 将 Markdown 转换为简单的 HTML，或者直接发纯文本。这里发送纯文本格式的 Markdown
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

    # 读取上次处理的记录
    last_video_id = None
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            last_video_id = data.get("video_id")

    # 对比是否为新视频
    if video_id == last_video_id:
        print(f"视频 {video_id} 已经处理过，任务结束。")
        return

    print(f"发现新视频：{title} (ID: {video_id})")
    
    # 提取字幕
    print("正在获取字幕...")
    transcript = get_transcript(video_id)
    if not transcript:
        print("无法获取字幕，跳过 AI 总结。")
        return

    # AI 总结
    print("正在请求 AI 总结...")
    summary = summarize_with_gemini(transcript, title)

    # 发送邮件
    print("正在发送邮件...")
    email_subject = f"【RhinoFinance 更新】{title}"
    send_email(email_subject, summary)
    print("邮件发送成功！")

    # 更新本地记录并保存
    with open(STATE_FILE, "w") as f:
        json.dump({"video_id": video_id, "title": title}, f)
    print("状态已更新。")

if __name__ == "__main__":
    main()