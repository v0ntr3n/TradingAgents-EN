# Lesson 5:Common mistakes in the discovery phase——From the pitfalls of veteran investors to a lightning protection guide in the AI era

> **Class hours**: 25 minutes | **difficulty**: ⭐ Getting Started | **prefix**: Lessons 1-4

> ⚠️ **Risk warning**:The content of this course is only for teaching platform functions.,AI The research report output does not constitute investment advice.,The final decision is yours.

## 🎯 What can you do after studying?

- identify**stock selection stage**The 7 most common mistakes
- know every mistake**Correct approach**
- Formed under the v3.0 platform**Lightning protection list**

## ⚠️ This lesson does not teach new functions,Only teach"What not to do"

You learned the first 4 lessons.:
- Lesson 1: Natural language filtering + Conditional filtering
- Lesson 2: Batch analysis(Single ≤ 10 only)
- Lesson 3: single stock research(5 level depth)
- Lesson 4: multi-role debate(Run all depths,The difference lies in the number of rounds)

This lesson is taught in reverse:**7 common mistakes newbies make**,Each error is based on real usage scenarios.

## Error 1:After reading the AI report, it is regarded as"buy signal"

### Error performance

> "AI The decision is'optimistic'!The market will open tomorrow and the positions will be full.!"

### Why is it wrong

v3.0 The system output is**Research reference**,**Not a trading order**. All batch analysis pages have a red tip at the top:

> ⚠️ **Important tips**:This analysis is only used for learning, research and public information compilation,No individual stock trading guidance is provided.

### Correct approach

Think of AI reporting as**second opinion**,combine:
- own risk tolerance
- Current market environment(Bull/Bear/Concussive)
- liquidity needs
- Already have a position correlation

AI decision making"optimistic"It's not 100% that you should buy it.,**Optimism is just"AI relatively confident"**,No"100% Yes". 

> 💡 When actually looking at the report,**Focus on 3 dimensions**rather than a single score:
> 1. **risk score** (0-1 numbers,The lower it is, the more controllable it is.)
> 2. **Assessment conclusion** Are the arguments sufficient?(Whether to list specific data/comparison?)
> 3. **core risk** list(How much is the risk and is it fatal?)

## Error 2:Report with different depths for the same stock"Come to a conclusion"

### Error performance

> 1 level theory"optimistic",3 level theory"Neutral",5 level theory"optimistic"——average,buy!

### Why is it wrong

Reports of varying depths**Conclusion may differ**,That's the value of having more depth.**"mingle"is wrong**,should watch**superlative conclusion**(The most complete information). 

### Correct approach

- same stock,See first**The most recent and deepest**report
- 5 level report > 4 level > 3 level(information density decreases)
- Don't"mingle"Different depths of conclusions

## Error 3:Don't look"Assessment conclusion",Just watch"Decision label"

### Error performance

> see directly"Decision label = optimistic"Just bought it,I didn't read the evaluation conclusion.

### Why is it wrong

report"🧾 research brief"in the card"Assessment conclusion"Paragraphs are AI**reasoning process**,tell you**why**Such a decision. If the argument is"Short-term oversold rebound",This and"long term value investment"It's a completely different story.

### Correct approach

1. Look first"🧾 research brief"in the card **Decision label** (Optimistic/cautious/neutral)
2. Look again **Assessment conclusion** (Arguments for why such a decision was made)
3. last look"⚠️ risk review"inside **Risk level/risk score/core risk**

"Assessment conclusion" may be very long(several hundred words),But**This is the core of AI reasoning**. 

## Error 4:Batch analysis of 50 stocks

### Error performance

> Submit all 50 screened animals for batch analysis at one time,Wait 3 hours for results.

### Why is it wrong

- **Backend hard limit:Maximum 10 at a time**
- Jingdong cloud version**single concurrency**,10 Only tasks are executed serially
- 3 level depth,10 only × 8 minutes = **80 minutes**Start

### Correct approach

- **divided into 5 batches**Submit(10 pieces per batch)
- JD Cloud users pay special attention to,**Avoid 1 stuffing**
- if yes**Pre-screening**(Just the general direction),Choose level 1-2 depth,2-5 one per minute
- stocks that really matter,take it out**Do individual stock research alone**(5 level)

## Error 5:Depend on"Natural language filtering"Do accurate backtesting

### Error performance

> "Use AI to screen the top 100 technology stocks that will gain momentum in 2024,See how it's doing now."

### Why is it wrong

Smart filtering(natural language)is based on**Current LLM intent understanding**,**Not a backtesting tool**. Enter the same description each time,AI Slightly different conditions may be inferred. In addition,v3.0 current**No backtest module is provided**. 

### Correct approach

- **Current stock picks** → Smart filtering(natural language)
- **Filter by precise conditions** → Advanced mode(condition builder)
- **Historical data query** → Use historical data query function

## Error 6:The entrance to Hong Kong and US stocks cannot be found.,Thought it was the system bug

### Error performance

> "Why does the system not have the function of analyzing Hong Kong and US stocks??There was a previous version!bug!"

### Why is it wrong

**No bug**. v3.0 Already**Take the initiative to offline Hong Kong and US stocks**front-end entrance,Currently**Only supports A shares and ETF funds**. backend code(`foreign_stock_service.py` 2402 OK)Although still there,But the front-end entrance**Remove all**. 

### Correct approach

- Switch the research scope to **A shares**(Main Board/GEM/Science and Technology Innovation Board/Beijing Stock Exchange)
- Want index/sector exposure?use **ETF fund**(510050/159919 Wait)
- Demand for Hong Kong and US stocks is temporarily unsupported(Waiting for subsequent versions)

## Error 7:see "risk score" If the number is low, assume it is"low risk"

### Error performance

> "risk score=0.3, Low risk score,Buy with confidence."

### Why is it wrong

"⚠️ risk review" Tab inside"**risk score**"Yes **0-1 decimal**,**The closer to 1, the higher the risk**,**The closer to 0, the lower the risk**. But**This is just the judgment of AI**,Not true.

### Correct approach

- look"**risk level**"label(More intuitive:low/medium/high)
- look"**Assessment conclusion**"risk discussion in paragraph
- look"**core risk**"list(Specific risk points)
- **The most critical**:look 🐻 Prudential Scenario Researcher Listed**Specific risk points**

"risk score"Low does not mean no risk,maybe just"AI Think risks are controllable". 

## ⚠️ v3.0 Important changes(Lightning protection related)

- ✅ **Compliance terminology**:No need"Buy/Sell",use"Optimistic/cautious/neutral"
- ✅ **Decision label**(Optimistic/cautious/neutral)It is the result of comprehensive judgment
- ✅ **Batch analysis single ≤ 10 only**
- ✅ **Hong Kong and US stocks are not available**(A shares only + ETF)
- ⚠️ All depths run debate roles(1-3 1 round for level 4, 2 rounds for level 4, 3 rounds for level 5)

## 🛠️ Practical operations:make one"Lightning protection list"

put you**past**List the mistakes you made when picking stocks:
1. Which error is it?
2. what happened then?
3. This time on the v3.0 platform**how to avoid**?

Save the list to "AI Memory",Before every stock selection in the future**Read it first**. 

## ❓ FAQ

**Q:What is the risk score?"high risk"?**
A: experience value(View page"risk level"Labels are more intuitive):
- 0.0-0.3:**low risk**(AI More confident that risks are controllable)
- 0.3-0.5:**medium risk**(Need attention)
- 0.5-0.8:**high risk**(cautious)
- 0.8+:**extremely high risk**(Basically not involved)

**Q:5 Level 3 and Level 3 both ran away.,Contradictory conclusion,Which one do you believe??**
A: letter**superlative**of(The most complete information). Low-level reports only view"general direction",5 level view"detailed reasoning". 

**Q:Intelligent filtering"I understand you want X"It's different from what I said,what to do?**
A: this is normal,AI in"Retell and clarify". **Do not click confirm directly**,Rather**Add corrections in the input box**:
- "No X,what i want is Y"
- "Add one more condition Z"
AI Understanding will be revised based on context.

**Q:Batch analysis task stuck on"Analyzing"a long time,Do you want to cancel and resubmit??**
A: **Don't worry yet**. Look at the progress bar in the "Task Center" menu:
- If the progress is moving(For example, from 30% to 35%),normal
- If the progress is stuck at 0% > 30 minutes,Can be canceled and resubmitted
Cancel using the right side of the task center"Cancel"button,Don't"Delete",Deleting will lose the history.

**Q:Data verification passed,The mission still failed,why?**
A: Data inspection only checks"Is the necessary data synchronized?". The task may also be due to:
- LLM call timeout(network problems)
- Token quota exhausted(Go to the Token usage page in the "Research Report" menu)
- Model is temporarily unavailable(Switch alternate model)
See error message,Locate specific reasons.

**Q:There are few key points in the research brief,Is it normal??**
A: Normal."🧾 research brief" Cards are summarized by AI,1-5 All are possible. When there are less than 2 items**Look especially at the conclusion paragraph of the evaluation**. 

## 📚 Further reading

- [Lesson 1:stock screen](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-01-discover/lesson-01-stock-screening.md)
- [Lesson 2:Batch analysis](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-01-discover/lesson-02-batch-analysis.md)
- [Lesson 3:An Introduction to Single Stock Research](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-01-discover/lesson-03-single-analysis-basic.md)
- [Lesson 4:multi-role debate](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-01-discover/lesson-04-single-analysis-multi-scenario.md)
- Phase 1 completed!enter [stage 2:Track](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-02-track/README.md)
