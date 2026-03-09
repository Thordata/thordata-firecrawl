# 🚀 Thordata Firecrawl 快速启动指南

**5 分钟上手 Thordata Firecrawl - 将任何网站转换为 AI 就绪数据**

---

## ⚡ 30 秒快速开始

### 方式 1: 使用云服务 (最快)

```bash
# 1. 获取 API Key
访问 https://dashboard.thordata.com 获取 THORDATA_SCRAPER_TOKEN

# 2. 测试云实例
curl -X POST "https://thordata-firecrawl-api.onrender.com/v1/scrape" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.thordata.com", "formats": ["markdown"]}'

# 3. 成功！响应包含 markdown 内容
```

### 方式 2: 本地运行 (开发)

```bash
# 1. 克隆仓库
git clone https://github.com/Thordata/thordata-firecrawl.git
cd thordata-firecrawl

# 2. 安装依赖
pip install -e ".[server,llm]"

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 THORDATA_SCRAPER_TOKEN

# 4. 启动服务
python run_server.py

# 5. 测试
curl -X POST "http://localhost:3002/v1/scrape" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.thordata.com", "formats": ["markdown"]}'
```

### 方式 3: Docker (推荐生产)

```bash
# 1. Docker Compose 一键启动
docker-compose up -d

# 2. 查看日志
docker-compose logs -f

# 3. 测试
curl http://localhost:3002/health
```

---

## 🎯 五大核心功能示例

### 1. Scrape - 单页面抓取

```bash
curl -X POST "http://localhost:3002/v1/scrape" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.thordata.com",
    "formats": ["markdown", "html"],
    "scrapeOptions": {
      "javascript": true,
      "wait": 2000
    }
  }'
```

**Python SDK:**
```python
from thordata_firecrawl import ThordataCrawl

client = ThordataCrawl(api_key="YOUR_TOKEN")

result = client.scrape(
    url="https://www.thordata.com",
    formats=["markdown"],
    javascript=True
)

print(result["data"]["markdown"])
```

---

### 2. Search - 网络搜索

```bash
curl -X POST "http://localhost:3002/v1/search" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "best web scraping tools 2026",
    "limit": 10,
    "engine": "google"
  }'
```

**返回搜索引擎结果列表**

> ⚠️ **延迟与超时建议**
>
> - 首次调用 / 冷启动 或访问 JS 很重的网站时，`scrape / search / crawl / agent` 可能需要 10–30 秒。
> - 建议客户端 HTTP 超时时间至少设置为 **30–60 秒**，特别是 `crawl` 和 `agent` 这类需要多步操作的接口。
> - 如果在 Windows 终端打印中文 / emoji 导致编码错误，可以先设置：
>   - PowerShell: `$env:PYTHONIOENCODING='utf-8'`
>   - CMD: `set PYTHONIOENCODING=utf-8`

---

### 3. Map - URL 发现

```bash
curl -X POST "http://localhost:3002/v1/map" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://doc.thordata.com",
    "search": "api"
  }'
```

**发现网站上所有相关 URL**

---

### 4. Crawl - 全站爬取

```bash
# 提交任务
curl -X POST "http://localhost:3002/v1/crawl" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://doc.thordata.com",
    "limit": 100,
    "maxDepth": 3,
    "includePaths": ["/docs/*"],
    "excludePaths": ["/privacy*"]
  }'

# 返回 job_id，轮询结果
curl "http://localhost:3002/v1/crawl/JOB_ID"
```

**异步爬取整个网站**

---

### 5. Agent - 智能提取

```bash
curl -X POST "http://localhost:3002/v1/agent" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Extract company founders information",
    "urls": ["https://www.thordata.com/about"],
    "schema": {
      "type": "object",
      "properties": {
        "founders": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": {"type": "string"},
              "role": {"type": "string"}
            }
          }
        }
      }
    }
  }'
```

**使用 LLM 提取结构化数据**

---

## 🧪 测试与诊断

### 快速诊断工具

```bash
# 检查部署状态
python diagnose.py --api-key YOUR_TOKEN

# 完整测试套件
python test_integration.py --api-key YOUR_TOKEN
```

### 在线 Playground

访问交互式 Playground:
- GitHub Pages: https://thordata.github.io/thordata-firecrawl-site/
- 本地：http://localhost:3002/playground

---

## 🔧 常见问题排查

### ❌ Agent 报错 "Failed to fetch"

**原因:** LLM 未配置或 Render 冷启动

**解决:**
```bash
# 1. 检查健康状态
curl http://localhost:3002/health

# 2. 确认 LLM 配置
# 确保 .env 中有:
OPENAI_API_KEY=your_key
OPENAI_API_BASE=https://api.siliconflow.cn/v1

# 3. Render 用户等待 30 秒 (冷启动)
```

### ❌ 认证失败 (401)

**原因:** API Key 错误

**解决:**
- 使用 `THORDATA_SCRAPER_TOKEN` (不是 `THORDATA_API_KEY`)
- 从 https://dashboard.thordata.com 获取新 key

### ❌ 超时 (Timeout)

**原因:** 目标网站加载慢或网络问题

**解决:**
```json
{
  "scrapeOptions": {
    "timeout": 60000,
    "maxRetries": 3
  }
}
```

---

## 📚 进阶用法

### 批量爬取

```python
urls = [
    "https://example.com/page1",
    "https://example.com/page2",
    "https://example.com/page3"
]

result = client.batch_scrape(urls, formats=["markdown"])
for item in result["results"]:
    print(f"Scraped {item['url']}: {len(item['data']['markdown'])} chars")
```

### 搜索 + 爬取组合

```python
result = client.search_and_scrape(
    query="web scraping API tutorial",
    search_limit=5,
    formats=["markdown"]
)

for item in result["results"]:
    print(f"Search result: {item['search']['title']}")
    print(f"Content: {item['scrape']['data']['markdown'][:200]}...")
```

### Webhook 通知 (Crawl)

```bash
curl -X POST "http://localhost:3002/v1/crawl" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://doc.thordata.com",
    "limit": 100,
    "webhook": {
      "url": "https://your-server.com/webhook",
      "headers": {"Authorization": "Bearer YOUR_SECRET"},
      "secret": "hmac-secret",
      "timeout": 30,
      "maxRetries": 5
    }
  }'
```

---

## ☁️ 部署选项

### 本地开发
- ✅ 完全免费
- ✅ 快速迭代
- ⚠️ 需要自己维护

### Render (免费套餐)
- ✅ 零配置部署
- ✅ HTTPS 端点
- ⚠️ 冷启动 15-30 秒
- ⚠️ 资源限制

### Railway ($5/月)
- ✅ 零冷启动
- ✅ 更好性能
- ✅ 简单部署
- 💰 性价比高

### 自托管 VPS
- ✅ 完全控制
- ✅ 可定制
- ⚠️ 需要运维

---

## 🔗 相关资源

### 文档
- 📖 [完整 README](README.md)
- 🔍 [故障排查指南](TROUBLESHOOTING.md)
- 📊 [优化报告](OPTIMIZATION_REPORT.md)

### 工具
- 🎮 [Interactive Playground](https://thordata.github.io/thordata-firecrawl-site/)
- 🐛 [GitHub Issues](https://github.com/Thordata/thordata-firecrawl/issues)
- 📦 [PyPI Package](https://pypi.org/project/thordata-firecrawl/)

### 社区
- 💬 Discord
- 🐦 Twitter
- 📧 Email Support

---

## 💡 最佳实践

### 1. 错误处理
```python
try:
    result = client.scrape(url="https://example.com")
    if result["success"]:
        process(result["data"])
    else:
        print(f"Scrape failed: {result['error']}")
except Exception as e:
    print(f"Exception: {e}")
    # 重试逻辑
```

### 2. 速率限制
```python
import time

urls = [...]  # 大量 URL
for url in urls:
    result = client.scrape(url=url)
    time.sleep(1)  # 避免触发速率限制
```

### 3. 缓存结果
```python
import hashlib
import json

def scrape_with_cache(url):
    cache_key = hashlib.md5(url.encode()).hexdigest()
    cache_file = f"cache/{cache_key}.json"
    
    if os.path.exists(cache_file):
        return json.load(open(cache_file))
    
    result = client.scrape(url=url)
    json.dump(result, open(cache_file, "w"))
    return result
```

---

## 🎯 下一步

1. ✅ **完成本快速入门** (5 分钟)
2. ✅ **运行诊断工具** (`python diagnose.py`)
3. ✅ **阅读 TROUBLESHOOTING.md** (深入了解)
4. ✅ **构建你的第一个爬虫项目**

---

## 🆘 需要帮助？

- 📖 查看 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- 🐛 提交 GitHub Issue
- 💬 加入 Discord 社区
- 📧 联系 support@thordata.com

---

**开始构建吧！** 🚀

*最后更新：2026-03-06 | 版本：v0.2.0*
