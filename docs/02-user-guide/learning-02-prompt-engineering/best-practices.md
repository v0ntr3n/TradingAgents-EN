# Prompt Word Engineering Best Practices

**Classification**: prompt word project  
**difficulty**: Advanced  
**reading time**: 12 minutes  
**Update date**: 2025-11-14

---

## 📋 Introduction

After mastering the basics of prompt words, how to write high-quality prompt words? This article summarizes the best practices of prompt word engineering to help you give full play to the capabilities of large language models.

---

## 🎯 core principles

### 1. Clarity

**principles**: Prompt words should be clear and unambiguous to avoid ambiguity.

❌ **Not clear**: 
```
analyze this
```

✅ **clear**: 
```
Please analyze the financial statements of the third quarter of 2024 of stock code 000001 (Ping An Bank),
Focus on revenue growth rate, net profit margin and ROE indicators.
```

### 2. Specificity

**principles**: Provide specific details and requirements.

❌ **general**: 
```
Give me some research observations
```

✅ **specific**: 
```
I am a long-term investor with medium risk appetite and a capital size of 1 million yuan.
Please based on the fundamental analysis of Ping An Bank (000001),
Give research observations on whether they are suitable as core concerns.
```

### 3. Structure

**principles**: Organize prompt words using a clear structure.

✅ **Structured example**: 
```
# role
You are a senior analyst focusing on banking stocks

# Task
Analyze the investment value of Ping An Bank (000001)

# data
- Stock price: 12.50 yuan
- P/E ratio:5.2
- ROE：10.5%

# request
1. Analyze valuation levels
2. Assess profitability
3. Give research observations

# Output format
Use Markdown, include titles and lists
```

### 4. Iteration optimization principle (Iteration)

**principles**: Continuously optimize the prompt words based on the output results.

**iterative process**: 
```
initial prompt word → View output → Found problem → Optimization prompt words → Test again
```

---

## 🛠️ Practical Tips

### Tip 1: Use delimiters

Use separators to clearly separate different sections.

**Example**: 
```
Please analyze the following stock data:

---data start---
Stock code:000001
Stock name: Ping An Bank
Current stock price: 12.50 yuan
P/E ratio:5.2
---end of data---

Please conduct analysis based on the above data.
```

**Common delimiters**: 
- `---`
- `###`
- `"""` (triple quotes)
- `<data>...</data>` (XML label)

### Tip 2: Specify the output length

Explicitly specify the length range for your responses.

**Example**: 
```
Please use 100-150 words to briefly analyze the investment value of Ping An Bank.
```

Or:
```
Please analyze the investment value of Ping An Bank in detail. The length of your answer is about 500-800 words.
```

### Tip 3: Ask for step-by-step thinking

Let AI demonstrate the thinking process and improve the quality of answers.

**Example**: 
```
Please analyze whether Ping An Bank (000001) is worth investing in.

Requirements:
1. First list the key factors that need to be considered in the analysis
2. Analyze each factor one by one
3. Finally, a comprehensive conclusion is given

Please show your thought process.
```

### Tip 4: Provide positive and negative examples

Explain what you want with positive and negative examples.

**Example**: 
```
Please analyze the investment value of Ping An Bank.

✅ Examples of good answers:
"Ping An Bank's price-to-earnings ratio is 5.2, lower than the industry average of 6.5, and its valuation is attractive.
However, it should be noted that the non-performing loan ratio is 1.2%, which is slightly higher than that of peers...."

❌ Examples of bad answers:
"This stock is great and I recommend buying it." (Contains trading instructions and does not comply with research-assisted positioning)

Please answer in the style of a good example.
```

### Tip 5: Set constraints

Tell the AI explicitly what it cannot do.

**Example**: 
```
Please analyze the investment value of Ping An Bank.

Constraints:
- Don't predict specific stock price increases or decreases
- don't give"Will rise", "Must fall"Waiting for absolute judgment
- Risk warning must be included
- Use objective, rational language
```

### Tip 6: Use templates

Create prompt word templates for common tasks.

**Stock Analysis Template**: 
```
you are a{Professional fields}Analyst.

Please analyze the stock{Stock code} ({Stock name}) of{Analysis Dimensions}. 

Current data:
{Data list}

Analysis requirements:
{Specific requirements}

Output format:
{Format description}
```

**Usage example**: 
```
You are a banking stock analyst.

Please analyze the valuation level and profitability of stock 000001 (Ping An Bank).

Current data:
- P/E ratio:5.2
- ROE：10.5%
- Net profit growth rate:8.5%

Analysis requirements:
1. Compared with industry average
2. Compare with historical data
3. Give an evaluation (underestimate/reasonable/overestimate)

Output format:
Use Markdown to include data comparison tables
```

---

## 📊 Best Practices for Stock Analysis

### 1. Fundamental analysis tips

**Template**: 
```
You are an investment advisor focused on fundamental analysis.

Please analyze{Stock code}Fundamentals of:

Financial data:
- P/E ratio:{PE}
- Price to Book Ratio:{PB}
- ROE：{ROE}
- Revenue growth rate:{revenue_growth}
- Net profit growth rate:{profit_growth}
- Asset-liability ratio:{debt_ratio}

Industry information:
- Industry:{industry}
- Industry status:{position}

Please analyze from the following perspectives:
1. Valuation level (compared to industry)
2. Profitability
3. Growth
4. financial health

Finally, a comprehensive rating (1-5 stars) and research observations are given.
```

### 2. Technical analysis tips

**Template**: 
```
You are an expert in technical analysis.

Please analyze{Stock code}The technical side:

Price data:
- Current price:{current_price}
- 20 Daily moving average:{ma20}
- 60 Daily moving average:{ma60}
- Recent highs:{high}
- Recent lows:{low}

Technical indicators:
- MACD：{macd}
- RSI：{rsi}
- Volume changes:{volume_change}

Please analyze:
1. Trend judgment (up/down/oscillation)
2. Support and pressure levels
3. technical indicator signals
4. Short-term trend prediction

Note: Technical analysis is for reference only and does not constitute investment advice.
```

### 3. Multiple stock comparison prompt words

**Template**: 
```
Please compare and analyze the following{N}only{Industry}Stocks:

{Stock List and Data}

Comparative dimensions:
1. Valuation level (PE, PB)
2. Profitability (ROE, net profit margin)
3. Growth (revenue growth, profit growth)
4. Financial health (debt ratio, cash flow)

Please present the comparison results in table form.
and explain their respective advantages and disadvantages,
The final recommendation is the most suitable{investment style}investor's stock.
```

---

## ⚠️ Common pitfalls

### Trap 1: Over-reliance AI

**question**: 
```
Please tell me which stock I should buy tomorrow
```

**Why is it bad**: 
- AI Unable to predict the market
- Investment decisions need to take personal circumstances into consideration
- May lead to blind following

**Correct approach**: 
```
Please analyze the fundamentals of the following 3 stocks,
Help me understand their investment value,
I make decisions based on my own risk appetite.
```

### Trap 2: Information overload

**question**: 
```
Please analyze the fundamentals, technical aspects, industry status, competitive advantages and financial status of this stock.
Historical Performance Future Prospects Management Quality Corporate Governance Shareholder Structure Dividend Policy...
```

**Why is it bad**: 
- Asking too many questions at once
- The answer may not be in depth enough
- Difficulty focusing

**Correct approach**: 
Ask questions multiple times, focusing on one topic each time.

### Trap 3: Lack of validation

**question**: Directly trust all outputs of AI

**Correct approach**: 
```
Please analyze Ping An Bank's financial data and indicate the source of the data.
I will verify the accuracy of this data myself.
```

---

## 💡 Advanced techniques

### Tip 1: Chain of Prompts

Break down complex tasks into multiple steps.

**Example**: 
```
Tips for the first step:
"Please list 10 key indicators that need to be paid attention to when analyzing bank stocks."

Tips for the second step:
"Based on the indicators you listed, please analyze Ping An Bank's data:
{data}"

Tips for step three:
"Based on the above analysis, please give research observations"
```

### Tip 2: Role Play

Let AI play different roles and obtain multi-angle analysis.

**Example**: 
```
Scenario 1: You are a conservative value investor
Please analyze Ping An Bank from the perspective of value investment

Scenario 2: You are an aggressive growth investor
Please analyze Ping An Bank from the perspective of growth investment

Scenario 3: You are a risk management expert
Please indicate the main risks of investing in Ping An Bank
```

### Tip 3: Self-criticism

Let the AI check its own answers.

**Example**: 
```
Step 1: Please analyze the investment value of Ping An Bank

Step 2: Please review your analysis and point out possible biases or deficiencies.

Step 3: Give a more comprehensive analysis based on self-criticism
```

---

## 📚 Summary

### core points

1. **Clear, specific, structured**It is the basis of good prompt words
2. **Use delimiters, templates, constraints**Improve efficiency
3. **For stock analysis**There is a special prompt word mode
4. **avoid pitfalls**: Over-reliance, information overload, lack of validation
5. **Advanced techniques**: Chain prompts, role play, self-criticism

### Practical suggestions

1. **Build your own prompt vocabulary**: Save commonly used prompt word templates
2. **Continuous optimization**: Continuously improve prompt words based on results
3. **Share and communicate**: Share prompt word experiences with other users
4. **keep thinking critically**: Verify the AI's output

---

## 🔗 Related resources

- 📖 [Prompt word basics](./prompt-basics.md)


