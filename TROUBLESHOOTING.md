# 🔍 Thordata Firecrawl 故障排查与优化指南

## 📋 核心功能检验报告

### ✅ 已完成的优化

#### 1. **Agent 功能错误处理增强**
- ✅ 添加 LLM 配置预验证
- ✅ 改进错误消息分类和提示
- ✅ 详细的日志记录和故障诊断

#### 2. **五大核心模式错误处理**
- ✅ **Scrape**: 增强认证/超时/连接错误识别
- ✅ **Search**: SERP API 错误分类
- ✅ **Map**: 种子页面获取失败处理
- ✅ **Crawl**: 异步 job 状态管理 + Webhook 重试
- ✅ **Agent**: LLM 服务可用性检查

#### 3. **Render 部署稳定性优化**
- ✅ 添加 disk 存储 (1GB /tmp)
- ✅ 配置 Oregon region 降低延迟
- ✅ 增加 timeout-keep-alive 参数
- ✅ 显式配置 PORT=10000
- ✅ 预装 LLM 依赖 `[server,llm]`

#### 4. **前端 Playground 错误诊断**
- ✅ 详细的错误分类提示
- ✅ Troubleshooting Tips 自动显示
- ✅ 响应时间监控
- ✅ 请求验证增强

---

## 🚨 常见问题快速诊断

### 问题 1: Agent 功能报错 `Failed to fetch`

**症状:**
```
❌ Error: Failed to fetch 
Troubleshooting: 
1. Check if the API server is running 
2. Verify the API URL is correct 
3. Ensure CORS is enabled
```

**根本原因:**
1. **API Server 未运行或休眠** (Render 免费套餐冷启动)
2. **CORS 配置不正确**
3. **API Key 类型错误**
4. **LLM 服务不可用**

**解决方案:**

#### 方案 1: 检查 API Server 状态
```bash
# 检查健康状态
curl https://your-render-url.onrender.com/health

# 期望响应:
{
  "status": "ok",
  "version": "0.2.0",
  "configuration": {
    "scraper_api": "configured",
    "llm_service": "configured",
    "llm_base_url": "https://api.siliconflow.cn/v1",
    "llm_model": "Qwen/Qwen2.5-7B-Instruct"
  },
  "timestamp": "2026-03-06T..."
}
```

如果 `/health` 无响应:
- ⏱ **等待 30-60 秒** (Render 冷启动)
- 🔄 **重新部署应用** (Render Dashboard → Manual Deploy)
- 📝 **检查环境变量** (确保 THORDATA_SCRAPER_TOKEN 已设置)

#### 方案 2: 验证 CORS 配置
在 Render Dashboard 中添加环境变量:
```bash
CORS_ALLOW_ORIGINS=https://thordata.github.io,https://your-domain.com
```

或者允许所有来源 (开发环境):
```bash
# 不设置 CORS_ALLOW_ORIGINS (默认允许所有)
```

#### 方案 3: 使用正确的 API Key
**重要:** 不同类型的操作需要不同的 token:

| 操作 | 需要的 Token | 获取位置 |
|------|-------------|----------|
| Scrape/Crawl/Map/Search | `THORDATA_SCRAPER_TOKEN` | [Thordata Dashboard](https://dashboard.thordata.com) |
| Agent (LLM 功能) | `OPENAI_API_KEY` + Scraper Token | SiliconFlow/OpenAI |

**前端 Playground 使用时:**
- 填入 `THORDATA_SCRAPER_TOKEN` (用于 scrape/crawl/map/search)
- Agent 功能还需要服务器配置 `OPENAI_API_KEY`

#### 方案 4: 检查 LLM 服务可用性
```bash
# 测试 SiliconFlow API
curl -X POST "https://api.siliconflow.cn/v1/chat/completions" \
  -H "Authorization: Bearer YOUR_SK" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

如果 LLM API 失败:
- ✅ 检查余额/配额
- ✅ 验证 API Base URL
- ✅ 确认模型名称正确

---

### 问题 2: Render 部署不稳定

**症状:**
- ⏱ 首次请求超时 (15-30 秒)
- 🔁 间歇性 502/503 错误
- 📉 高延迟响应

**原因分析:**
Render 免费套餐的限制:
1. **实例休眠**: 15 分钟无请求自动休眠
2. **冷启动延迟**: 唤醒需要 15-30 秒
3. **资源限制**: 512MB RAM, 共享 CPU
4. **网络波动**: 偶尔连接重置

**优化方案:**

#### 方案 1: 保持实例活跃 (Ping 服务)
使用外部监控服务定期 ping API:

```bash
# UptimeRobot (免费，5 分钟间隔)
# Setup：https://uptimerobot.com/
# Monitor Type: HTTP(s)
# URL: https://your-render-url.onrender.com/health
# Interval: 5 minutes
```

#### 方案 2: 升级到付费套餐
Render 专业套餐 ($7/月):
- ✅ 永不休眠
- ✅ 更快 CPU
- ✅ 512MB 独占内存
- ✅ 更低延迟

#### 方案 3: 迁移到更稳定平台
推荐替代方案:

| 平台 | 价格 | 优点 | 缺点 |
|------|------|------|------|
| **Railway** | $5/月 | 性能更好，无冷启动 | 需要信用卡 |
| **Fly.io** | ~$2/月 | 全球边缘节点 | 配置复杂 |
| **Vercel** | 免费 | 零配置 | Serverless 限制 |
| **自托管 VPS** | ~$5/月 | 完全控制 | 需要运维 |

---

### 问题 3: 五大模式功能异常

#### Scrape 模式失败
**检查清单:**
```bash
# 1. 验证基础 scrape
curl -X POST "https://your-render-url.onrender.com/v1/scrape" \
  -H "Authorization: Bearer YOUR_SCRAPER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.thordata.com", "formats": ["markdown"]}'

# 期望输出:
{
  "success": true,
  "data": {
    "markdown": "# Thordata..."
  }
}
```

**常见错误:**
- ❌ `Authentication failed` → 检查 API key
- ❌ `Request timeout` → 增加 wait 时间或启用 js_render
- ❌ `No content returned` → 检查 URL 可访问性

#### Crawl 模式失败
**调试步骤:**
```bash
# 1. 提交 crawl job
curl -X POST "https://your-render-url.onrender.com/v1/crawl" \
  -H "Authorization: Bearer YOUR_SCRAPER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://doc.thordata.com",
    "limit": 5,
    "maxDepth": 2
  }'

# 返回:
{
  "success": true,
  "id": "job-xxx",
  "url": "/v1/crawl/job-xxx"
}

# 2. 轮询状态
curl https://your-render-url.onrender.com/v1/crawl/job-xxx

# 期望状态:
{
  "status": "completed",
  "total": 5,
  "completed": 5,
  "data": [...]
}
```

**优化建议:**
- ⚙️ 设置 `MAX_CONCURRENT_CRAWLS=2` (避免资源耗尽)
- ⚙️ 设置 `JOB_TTL_SECONDS=3600` (1 小时后清理)
- ⚙️ 启用 Webhook 通知 (避免频繁轮询)

#### Agent 模式失败
**完整测试流程:**

```bash
# 1. 检查 LLM 配置
curl https://your-render-url.onrender.com/health
# 确认 "llm_service": "configured"

# 2. 简单 agent 请求
curl -X POST "https://your-render-url.onrender.com/v1/agent" \
  -H "Authorization: Bearer YOUR_SCRAPER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Extract company name",
    "urls": ["https://www.thordata.com"],
    "formats": ["markdown"]
  }'

# 成功响应:
{
  "success": true,
  "data": {
    "company_name": "Thordata"
  },
  "sources": ["https://www.thordata.com"]
}

# 失败响应 (LLM 未配置):
{
  "success": false,
  "error": "LLM service not configured..."
}
```

---

## 🧪 全面测试脚本

### 本地开发环境测试

```bash
#!/bin/bash
# test_all_endpoints.sh

BASE_URL="http://localhost:3002"
API_KEY="your-test-key"

echo "🔍 Testing Thordata Firecrawl API..."

# 1. Health Check
echo -e "\n📊 1. Health Check"
curl -s "$BASE_URL/health" | jq .

# 2. Scrape Single Page
echo -e "\n📄 2. Scrape Single Page"
curl -s -X POST "$BASE_URL/v1/scrape" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.thordata.com", "formats": ["markdown"]}' | jq '.success'

# 3. Search
echo -e "\n🔍 3. Search"
curl -s -X POST "$BASE_URL/v1/search" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "web scraping API", "limit": 3}' | jq '.success'

# 4. Map
echo -e "\n🗺 4. Map"
curl -s -X POST "$BASE_URL/v1/map" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.thordata.com"}' | jq '.success'

# 5. Crawl (Async Job)
echo -e "\n🕷 5. Crawl (Async)"
JOB_RESPONSE=$(curl -s -X POST "$BASE_URL/v1/crawl" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.thordata.com", "limit": 2}')
JOB_ID=$(echo $JOB_RESPONSE | jq -r '.id')
echo "Job ID: $JOB_ID"

# Poll job status
sleep 5
curl -s "$BASE_URL/v1/crawl/$JOB_ID" | jq '.status'

# 6. Agent (if LLM configured)
echo -e "\n🤖 6. Agent"
curl -s -X POST "$BASE_URL/v1/agent" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Extract company name",
    "urls": ["https://www.thordata.com"],
    "formats": ["markdown"]
  }' | jq '.success'

echo -e "\n✅ All tests completed!"
```

### 生产环境测试 (Render)

```bash
#!/bin/bash
# test_render_deployment.sh

RENDER_URL="https://your-app.onrender.com"
API_KEY="your-scraper-token"

echo "🚀 Testing Render Deployment..."

# 1. Warm up (avoid cold start)
echo "⏰ Warming up instance..."
curl -s "$RENDER_URL/health" > /dev/null

# 2. Full test suite
./test_all_endpoints.sh BASE_URL=$RENDER_URL API_KEY=$API_KEY

# 3. Load test (optional)
echo -e "\n💪 Load Test (10 concurrent requests)"
for i in {1..10}; do
  curl -s -X POST "$RENDER_URL/v1/scrape" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"url": "https://www.thordata.com", "formats": ["markdown"]}' &
done
wait

echo -e "\n✅ Load test completed!"
```

---

## 📈 性能优化建议

### 1. 并发控制
```bash
# .env 配置
MAX_CONCURRENT_CRAWLS=2          # 同时运行的 crawl jobs
RATE_LIMIT_TOKEN_RPM=60          # 每 token 每分钟请求数
RATE_LIMIT_IP_RPM=120            # 每 IP 每分钟请求数
```

### 2. 超时设置
```python
# 在 scrapeOptions 中设置合理超时
{
  "timeout": 30000,              # 30 秒超时
  "maxRetries": 3,               # 最多重试 3 次
  "javascript": true,            # 启用 JS 渲染 (如需)
  "wait": 2000                   # 等待 2 秒 (动态内容)
}
```

### 3. 响应大小控制
```bash
# 限制响应大小防止 OOM
MAX_RESPONSE_SIZE=10485760       # 10MB

# 使用分页获取大数据集
GET /v1/crawl/{job_id}?offset=0&limit=50
GET /v1/crawl/{job_id}?offset=50&limit=50
```

---

## 🔧 持续集成建议

### GitHub Actions 自动测试

```yaml
# .github/workflows/test.yml
name: API Tests

on:
  push:
    branches: [main]
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours

jobs:
  test-api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -e ".[server,llm]"
      
      - name: Run unit tests
        run: python test_api.py
      
      - name: Test Render deployment
        env:
          RENDER_URL: ${{ secrets.RENDER_URL }}
          API_KEY: ${{ secrets.THORDATA_SCRAPER_TOKEN }}
        run: |
          chmod +x test_render_deployment.sh
          ./test_render_deployment.sh
```

---

## 📝 总结

### ✅ 已完成优化
1. ✅ Agent 功能错误处理增强
2. ✅ 五大模式全面错误分类
3. ✅ Render 部署配置优化
4. ✅ 前端 Playground 诊断能力提升

### ⚠️ 待改进领域
1. **监控告警**: 添加 Prometheus/Grafana 监控
2. **分布式追踪**: Jaeger/SkyWalking 集成
3. **自动扩缩容**: K8s HPA 配置
4. **缓存层**: Redis 缓存热点数据
5. **数据库持久化**: 替换 in-memory job store

### 🎯 最佳实践
1. **开发环境**: 本地运行 + Docker Compose
2. **测试环境**: Render 免费套餐 + UptimeRobot
3. **生产环境**: Railway/Fly.io 付费套餐 + 监控告警
4. **企业级**: 自托管 K8s + Redis + PostgreSQL

---

## 🔗 相关资源

- 📚 [官方文档](https://github.com/Thordata/thordata-firecrawl)
- 🎮 [Interactive Playground](https://thordata.github.io/thordata-firecrawl-site/)
- 🐛 [Issue Tracker](https://github.com/Thordata/thordata-firecrawl/issues)
- 💬 [Discord Community](https://discord.gg/...)

---

**最后更新:** 2026-03-06  
**版本:** v0.2.0
