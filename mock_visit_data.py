import random
from datetime import datetime, timedelta
from app.models.user import WebsiteVisit, SessionLocal

db = SessionLocal()

# Clear existing to be clean (optional, maybe keep my manual ones)
# db.query(WebsiteVisit).delete()

referrers = [
    "https://www.baidu.com/s?wd=跃云AIOps", 
    "https://blog.csdn.net/article/123",
    "https://www.google.com/",
    "https://www.zhihu.com/question/456",
    "Direct",
    "https://mp.weixin.qq.com/"
]

uas = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]

print("Generating mock visits...")
for i in range(7):
    day = datetime.utcnow() - timedelta(days=i)
    # Random daily count 50-200
    count = random.randint(50, 200)
    
    for _ in range(count):
        # Random hour
        h = random.randint(0, 23)
        m = random.randint(0, 59)
        ts = day.replace(hour=h, minute=m)
        
        v = WebsiteVisit(
            ip=f"192.168.{random.randint(1,255)}.{random.randint(1,255)}",
            country="China",
            city="Shanghai",
            referrer=random.choice(referrers),
            user_agent=random.choice(uas),
            timestamp=ts
        )
        db.add(v)

db.commit()
print("Done.")
