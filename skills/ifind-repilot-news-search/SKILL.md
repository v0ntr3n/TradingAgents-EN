---
name: ifind-repilot-news-search
description: Semantically search all market financial information (news, public opinion, market dynamics, etc.) through the question and return news fragment information related to the question. Use this skill when you need to retrieve financial news, market information, industry trends, company public opinion and other information.
metadata:  {"openclaw":{"emoji":"📰︎","requires":{"bins":["python3"]}}}
---

## Overview

This skill queries (vector search) all market financial information through natural language questions. It calls the encapsulated Python script, sends a request to the Flush data interface, and returns the news list information related to the question. Supports querying by time range.

## Prerequisites

### environment dependence

- Python 3.x
- Standard library:`json`, `urllib`, `pathlib`
- No need to install third-party libraries
- Note 1: If `python3` Command not available (common on Windows), use instead `python`
- Note 2:`<skill_dir>` It is the full path of the directory where the current skill is located. Please obtain it automatically based on the current context.

### First time configuration

Before using the skill for the first time, you need to configure the authentication token.

1. Users are prompted to obtain tokens from the Feiyan platform first. Platform address: https://repilot.51ifind.com/ , Menu path:Business Management -> Skills Skill library.
2. After the user provides the token, run the following command to configure the token:
```bash
python3 <skill_dir>/scripts/fetch_data.py --set-token <your_auth_token>
```
3. Check if token is configured:
```bash
python3 <skill_dir>/scripts/fetch_data.py --check-token
```

Note: The configuration file is located at:`~/.config/ifind-repilot/config.json`

## Usage

### Basic query

```bash
python3 <skill_dir>/scripts/fetch_data.py "<Natural language query statement>"
```

### Query with time range

```bash
python3 <skill_dir>/scripts/fetch_data.py "<Natural language query statement>" --start-date <start date> --end-date <end date>
```

Date format:`YYYY-MM-DDTHH:MM:SS`, For example `2025-01-01T00:00:00`

Date parameters can be placed before or after the query statement:

```bash
# Method 1: Date parameter first
python3 <skill_dir>/scripts/fetch_data.py --start-date 2025-01-01T00:00:00 --end-date 2026-01-01T00:00:00 "Federal Reserve Interest Rate Policy"

# Method 2: Date parameter comes last
python3 <skill_dir>/scripts/fetch_data.py "Federal Reserve Interest Rate Policy" --start-date 2025-01-01T00:00:00 --end-date 2026-01-01T00:00:00
```

### Query example

| Query content | command |
|---------|------|
| Federal Reserve Interest Rate Policy | `python3 <skill_dir>/scripts/fetch_data.py "Federal Reserve Interest Rate Policy"` |
| Flush Latest News | `python3 <skill_dir>/scripts/fetch_data.py "Flush"` |
| 2025 annual fed interest rate policy | `python3 <skill_dir>/scripts/fetch_data.py "Federal Reserve Interest Rate Policy" --start-date 2025-01-01T00:00:00 --end-date 2025-12-31T23:59:59` |


### Return format

The script directly returns the JSON data of the query results, including the following fields:

| Field | Type | Description |
|------|------|------|
| `total` | int | Total number of news retrieved |
| `status_code` | int | Status code, 0 means success |
| `status_msg` | string | status information |
| `data` | array | News list |

Each news item contains the following fields:

| Field | Type | Description |
|------|------|------|
| `title` | string | News headline |
| `summary` | string | news summary |
| `url` | string | News original link |
| `channel` | string | Channel type |
| `publish_time` | int | Release time (Unix timestamp) |
| `publish_date` | string | Release time (format:YYYY-MM-DD HH:MM:SS)  |
| `score` | int | Relevance score |
| `extra` | object | Extended information (such as `publish_source` Source) |

Return example:

```json
{
  "total": 15,
  "status_code": 0,
  "data": [
    {
      "title": "Dragon and Tiger List | Tonghuashun hit the limit today, and the two institutions sold a total of 641 million yuan in net sales",
      "summary": "11 On March 7, Tonghuashun hit the daily limit today, with a transaction volume of 13.206 billion yuan....",
      "url": "https://www.jiemian.com/article/11954485.html",
      "channel": "news",
      "publish_time": 1730968311,
      "publish_date": "2024-11-07 16:31:51",
      "score": 100,
      "extra": {
        "publish_source": "interface news"
      }
    }
  ],
  "status_msg": "OK"
}
```

### Error handling

| error message | Reason | Solution |
|----------|------|----------|
| `Please configure first auth_token` | not set token | Prompt the user to obtain and send the token. After receiving the token, run `--set-token` Configuration |
| `API HTTP Error` | Request failed | Check network or API address |
| `network error` | Unable to connect | Check network connection |
| `API Return failure` | interface returns error | View specific error messages |
| `API HTTP Error: 429` | Trigger request limit for the day | Remind users to check usage information on Feiyan platform |
| `API HTTP Error: 401` | The token is missing or invalid | Remind the user to check whether the token is correct |
| `API HTTP Error: 403` | No permission to access the interface | No permission to access the interface |

## enforce rules

1. First determine whether the user request or task requires financial information retrieval.
2. If financial information retrieval is required, a suitable natural language query statement is generated as a parameter to call the script based on the user's request content and thinking.
3. If the request returns no retrieved data, or the returned data does not meet expectations, you can try to generate a new natural language query statement and query again.
4. Don't make up any financial information. If the script fails or returns empty results, the reason for failure or data not being retrieved should be clearly stated.
5. Reorganize and refine script output; retain important data from news titles, sources, and summaries.
6. When a 401, 403, or 429 error occurs, please do not try again and directly remind the user of the error content returned by the skill.