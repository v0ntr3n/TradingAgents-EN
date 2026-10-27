# Prompt word basics

**Classification**: prompt word project  
**difficulty**: Getting Started  
**reading time**: 10 minutes  
**Update date**: 2025-11-14

---

## 📋 Introduction

Prompts are the key to interacting with large language models. A good prompt word can allow AI to understand your needs more accurately and generate high-quality answers. This article will introduce the basic knowledge of prompt words and help you master the skills of talking to AI.

### learning objectives

- Understand what cue words are
- Master the basic structure of prompt words
- Learn to write clear and effective prompt words
- Learn about common prompt word mistakes

---

## 🎯 What is a cue word?

### definition

**Prompt**is the input text you send to a large language model to instruct the model to produce a specific output.

Simply put, a prompt word is what you say to the AI, telling it what you want.

### The role of prompt words

```
your prompt word → large language model → AI answer
```

**Example**: 

❌ **vague prompt word**: 
```
Analyze this stock
```

✅ **clear cue word**: 
```
Please analyze the investment value of stock code 000001 (Ping An Bank), including:
1. Fundamental analysis (financial indicators, profitability)
2. Technical analysis (price trends, technical indicators)
3. Industry status and competitive advantages
4. Research Observations and Risk Tips
```

---

## 🏗️ Basic structure of prompt words

A good prompt usually contains the following parts:

### 1. Role setting (Role)

Tell the AI what role it should play.

**Example**: 
```
You are a senior stock analyst with more than 10 years of experience in analyzing the A-share market.
```

**Why is it important**: 
- Help AI understand from what angle it should answer
- Improve the professionalism and pertinence of answers

### 2. Task description (Task)

Clearly state what you want the AI to do.

**Example**: 
```
Please analyze the investment value of Ping An Bank (000001).
```

**Main points**: 
- Use clear verbs: analyze, summarize, compare, evaluate
- Specify specific objects: stock code, company name
- Describe the scope of analysis: time period, dimensions

### 3. Context information (Context)

Provide necessary background information and data.

**Example**: 
```
Current stock price: 12.50 yuan
P/E ratio:5.2
Price to Book Ratio:0.6
Increase and decrease in the past year:-8.5%
Industry: Banking
```

**Why is it important**: 
- Let AI analyze based on actual data
- Avoid AI fabricating information (illusion)

### 4. Output format (Format)

Specify the format you want your answer to be in.

**Example**: 
```
Please output in the following format:

## fundamental analysis
- Financial indicator evaluation
- Profitability analysis

## Technical analysis
- price trend
- Technical indicators

## research observation
- Research conclusion tendency: optimistic/cautious/neutral
- Reason:...
```

**Common formats**: 
- Markdown Format
- JSON Format
- table format
- list format

### 5. Constraints

Set limits and requirements for answers.

**Example**: 
```
Requirements:
- Answer length should not exceed 500 words
- Use concise language and avoid jargon
- Risk warning must be included
- Don't give specific buying and selling recommendations
```

---

## ✍️ Tips for Writing Effective Prompt Words

### Tip 1: Be specific

❌ **blurry**: 
```
How is this stock?
```

✅ **specific**: 
```
Please analyze the investment value of Ping An Bank (000001) from three dimensions: fundamentals, technical aspects, and industry status.
```

### Tip 2: Provide sufficient information

❌ **Insufficient information**: 
```
Analyze bank stocks
```

✅ **enough information**: 
```
Please analyze Ping An Bank (000001):
- Current stock price: 12.50 yuan
- P/E ratio: 5.2 (industry average: 6.5)
- ROE：10.5%
- Non-performing loan ratio:1.2%
```

### Tip 3: Step-by-step guidance

❌ **Asking for too much at once**: 
```
Analyzes all aspects of this stock and gives detailed research observations and risk assessments as well as future forecasts
```

✅ **step by step**: 
```
Step 1: Please analyze the fundamentals of Ping An Bank first
Step 2: Evaluate its investment value based on fundamental analysis
Step Three: List Key Risk Factors
```

### Tip 4: Use examples

Tell the AI what output you want through examples.

**Example**: 
```
Please analyze stocks in the following sample format:

Example:
Stock: Kweichow Moutai (600519)
Rating:★★★★★
Reason: Industry leader, high brand value, strong profitability
Risks: high valuation, policy risks

Now please analyze: Ping An Bank (000001)
```

### Tip 5: Set character and tone

**Example**: 
```
You are a prudent value investor. Please analyze Ping An Bank in an objective and rational tone.
Avoid exaggerated statements and focus on long-term investment value.
```

---

## 🚫 Common mistakes

### Mistake 1: Prompt word is too short

❌ **too brief**: 
```
000001
```

**question**: AI don't know what you want

### Mistake 2: Asking too many questions at once

❌ **Too many questions**: 
```
Analysis of 000001's fundamentals, technical aspects, industry status, competitive advantages, financial status, future prospects, research and observation, risk factors...
```

**question**: The answer may not be in depth enough

### Mistake 3: Using vague words

❌ **blurry**: 
```
Is this stock a good stock?
```

**question**: "good"The standards are not clear

✅ **clear**: 
```
From the perspective of long-term investment value, analyze the fundamental trends and main risks of this stock
```

### Mistake 4: Not providing necessary information

❌ **Missing information**: 
```
Analyze this stock
```

**question**: AI I don't know which stock it is

### Mistake 5: Expecting AI to predict the future

❌ **unreasonable expectations**: 
```
Tell me whether this stock will go up or down tomorrow
```

**question**: AI It is impossible to predict the stock market, and such prompt words will lead to unreliable answers.

---

## 💡 Practical examples

### Example 1: Single Stock Analysis

**Excellent prompt words**: 
```
You are a senior stock analyst. Please analyze the investment value of Ping An Bank (000001).

Current data:
- Stock price: 12.50 yuan
- P/E ratio:5.2
- Price to Book Ratio:0.6
- ROE：10.5%
- Industry: Banking

Please analyze from the following perspectives:
1. Valuation level (compared to industry)
2. Profitability
3. Growth
4. risk factors

Output format:
- Use Markdown format
- Each part should not exceed 150 words
- Finally, give a comprehensive evaluation (1-5 stars)
```

### Example 2: Stock comparison

**Excellent prompt words**: 
```
Please compare and analyze the following two bank stocks:

Stock A: Ping An Bank (000001)
- P/E ratio:5.2
- ROE：10.5%
- Non-performing loan ratio:1.2%

Stock B: China Merchants Bank (600036)
- P/E ratio:6.8
- ROE：15.2%
- Non-performing loan ratio:0.9%

Please compare from the three dimensions of valuation, profitability and asset quality.
And explain which stock is better for value investors.
```

---

## 📚 Summary

### Key takeaways

1. **Prompt words are the key to talking to AI**
2. **Good prompt words include**: Role, task, context, format, constraints
3. **Writing skills**: Specific, clear, sufficient information, and step-by-step guidance
4. **avoid mistakes**: Too brief, too many questions, unreasonable expectations

### Next step to learn

- 📖 [Prompt Word Engineering Best Practices](./best-practices.md)


---

## ❓ Practice questions

Try improving the following prompt words:

**practice 1**: 
```
❌ Original prompt: Analyze Moutai
✅ After improvement:_______________
```

**practice 2**: 
```
❌ Original prompt: Can this stock rise?
✅ After improvement:_______________
```

---


