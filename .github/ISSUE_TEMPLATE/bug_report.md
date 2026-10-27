---
name: 🐛 Bug Report
about: Report a bug to help us improve
title: '[BUG] '
labels: ['bug', 'needs-triage']
assignees: ''
---

## 🐛 Bug Description

**Issue Type:**
- [ ] 🚀 Startup/Installation Issue
- [ ] 🌐 Web Interface Issue
- [ ] 💻 CLI Tool Issue
- [ ] 🤖 LLM API Issue
- [ ] 📊 Data Acquisition Issue
- [ ] 🐳 Docker Deployment Issue
- [ ] ⚙️ Configuration Issue
- [ ] 🔄 Feature Malfunction
- [ ] 🐌 Performance Issue
- [ ] Other: ___________

**Brief description:**
Provide a clear and concise description of the bug.

**Expected behavior:**
Describe what you expected to happen.

**Actual behavior:**
Describe what actually happened.

## 🔄 Steps to Reproduce

Please provide detailed steps to reproduce the issue:

1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

## 📱 Environment

**System Info:**
- OS: [e.g. Windows 11, macOS 13, Ubuntu 22.04]
- Python Version: [e.g. 3.11.0]
- Project Version: [e.g. v3.0.0]

**Installation Method:**
- [ ] Local Installation
- [ ] Docker Deployment
- [ ] Other: ___________

**Dependencies:**
```bash
# Please run the following command and paste the result
pip list | grep -E "(streamlit|langchain|openai|requests|tushare|akshare|baostock)"
```

**Browser Info (for Web Interface issues only):**
- Browser: [e.g. Chrome 120, Firefox 121, Safari 17]
- Version:
- Incognito mode: [ ] Yes [ ] No

## 📊 Configuration

**API Configuration:**
- [ ] Tushare Token configured
- [ ] DeepSeek API Key configured
- [ ] DashScope API Key configured
- [ ] FinnHub API Key configured
- [ ] Database configured

**Data Sources:**
- Chinese Stock Source: [tushare/akshare/baostock]
- US Stock Source: [finnhub/yfinance]

## 📝 Error Logs

**Console Errors:**
```
Please paste the complete error message and stack trace
```

**Log Files:**
```bash
# If logging is enabled, please provide relevant logs

# Web app logs
tail -n 50 logs/tradingagents.log

# Docker logs
docker-compose logs web
```

**Network Request Errors:**
If this is an API call issue, please provide:
- API response status code
- Error response content
- Request parameters (redact sensitive info)

## 📸 Screenshots

If applicable, add screenshots to help explain your problem.

## 🔍 Additional Context

Add any other context about the problem here.

## ✅ Checklist

Please confirm that you have:
- [ ] Searched existing issues to ensure this is not a duplicate
- [ ] Tested with the latest version of the code
- [ ] Provided complete error messages
- [ ] Included steps to reproduce
- [ ] Filled out the environment information

---

**Thank you for your feedback! We will address this issue as soon as possible.**
