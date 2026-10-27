---
name: ifind-repilot-finance-data-search
description: Use natural language to query financial data, support A-share stocks, funds, futures and other listed products, covering basic information, financial data, daily market information, position information and various analysis indicators and other data. It also supports macroeconomic data, including world economic data, global economic data, Chinese economic data, regional economic data, industry economic data, interest rate trend data, commodity data and special data, etc. Use this skill when you need to query the above financial related data queries.
metadata:  {"openclaw":{"emoji":"🔍︎","requires":{"bins":["python3"]}}}
---

## Overview

This skill queries financial data through natural language. By calling the encapsulated Python script, a request is sent to the Flush financial data interface and semi-structured financial data is returned.

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

### Query example

| Query content | command |
|---------|------|
| Flush closing price | `python3 <skill_dir>/scripts/fetch_data.py "Flush closing price"` |
| Moutai stock price | `python3 <skill_dir>/scripts/fetch_data.py "Kweichow Moutai current stock price"` |
| Apple earnings report | `python3 <skill_dir>/scripts/fetch_data.py "Apple's most recent quarterly revenue and profits"` |
| Shanghai Composite Index | `python3 <skill_dir>/scripts/fetch_data.py "Shanghai Composite Index Today's Quotes"` |
| stock comparison | `python3 <skill_dir>/scripts/fetch_data.py "Comparison of BYD and NIO stock prices"` |

### Return format

The script directly returns the text content of the query result, which is usually a combination of text and Markdown table format. Example:

```
Extract data: Data Browser
|Securities code|Securities abbreviation|Closing price (yuan)|
|---|---|---|
|300033.SZ|Flush|291.74|

Extract data:FinQuery
|Stock code|stock abbreviation|Date|closing price:Loss of power|
|---|---|---|---|
|300033.SZ|Flush|20250808|287.78|
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
| `No result yet` | No data was retrieved for the current question, and it is not a token permission issue. | Try to generate a new natural language query statement and query again |


## enforce rules

1. First determine whether the user request or task requires financial data retrieval.
2. If financial data retrieval is required, a suitable natural language query statement is generated as a parameter to call the script based on the user's request content and thinking.
3. If the question contains a request for financial data with an unclear time range, default to querying for the most recent disclosed quarter or most recent fiscal year, and clearly state the default time range in the answer.
4. If the request returns no retrieved data, or the returned data does not meet expectations, you can try to generate a new natural language query statement and query again.
5. Don't make up any financial numbers. If the script fails or returns empty results, the reason for failure or data not being retrieved should be clearly stated.
6. Distill the key data in the script output into concise conclusions; if there are tables, keep them first.
7. When a 401, 403, or 429 error occurs, please do not try again and directly remind the user of the error content returned by the skill.