# Lesson 1:stock screen——Find the ones worth researching from 6,000 stocks

> **Class hours**: 20 minutes | **difficulty**: ⭐ Getting Started | **prefix**: None

> ⚠️ **Risk warning**:The content of this course is only for teaching platform functions.,AI The research report output does not constitute investment advice.,The final decision is yours.

> ⚠️ **Risk warning**:This article is a tutorial on how to use the system functions,**Does not constitute any investment advice**. AI Output results(Decision labels, risk scores, assessment conclusions)For research reference only,All investment decisions are made by users themselves,You are responsible for your profits and losses.

## 🎯 What can you do after studying?

- use**a common saying**tell AI"What stocks do I want?",AI Automatic filtering
- use"**Advanced mode**"Do fine screening(contains"Common conditions"and"Advanced fields"two floors)
- filter results**Send batch analysis with one click**

## 🤔 Why screening is needed?What will happen if you don't filter??

A The stock market has **5000+ only stocks**(Still increasing),You can't just look at them.**Search for codes directly or listen to recommendations from others**pain points:

| way | question |
|------|------|
| 5000 full market research | There is simply not enough time and energy,1 Only in-depth research takes 10-20 minutes |
| listen"Hot stocks"Recommended | Recommended by others"Hotspot"often**It has risen a lot**of,Chasing high is risky |
| Look at the rankings | The ranking is**historical performance**,The future may not necessarily continue |
| Pick your brain | no systematic approach,Completely based on feeling,**Will lose money in the long run** |

**The nature of screening**:use**set of rules**Narrow down 5000 to just you.**Can study it**scale(50-100 only),Research further.

> 💡 **funnel idea**:5000 only → Intelligent screening reduces the number to 100-500 → Advanced mode refined to 50-100 pieces → Batch analysis studies → Finally choose 5-10

## ⚠️ v3.0 Important changes

- ✅ **New**:**Smart filtering(natural language conversational)It is the core function of v3.0**,v2.x The times are only"Advanced mode"conditional form
- ✅ **Default tab switching**:Enter the filter page and display it by default"Smart filtering"(natural language),no longer"Advanced mode"
- ✅ **Support multiple rounds of dialogue**:AI Will proactively state your needs,You can ask"Add another condition"
- ⚠️ **Platform scope**:Only supports **A Stocks and ETFs**,The front-end entrance to Hong Kong and US stocks has been offline

## 📍 entrance(not found?Proceed this way)

| advance method | How to operate |
|------|---------|
| sidebar | The navigation bar on the far left of the page,Find"stock analysis"→"stock screen" |
| Home page | Find it in the card area on the homepage"Stock Picking Assistant"card(Card upper right corner with"v3.0"small label) |

> 💡 **Still can't find it?** Open AI Assistant,ask"How to enter stock screening?",The assistant will guide you step by step.

## 🖱️ Operation steps(Follow the 5 steps)

### steps 1:Enter filters

1. Use any of the above methods to enter the "Stock Screening" page
2. After entering,you will see**two Tab**:On the left is"**Smart filtering**",On the right is"**Advanced mode**"
3. The system default is at"Smart filtering" Tab,Just use it directly

> Page layout:On the left is"Filter history"column,To the right of the center is the dialog input box.

> ⏱️ **Elapsed time expected**:
> - Load filter page:1-2 seconds
> - AI Restate your needs:5-10 seconds
> - Result card:1-3 seconds
> - The entire process is usually completed within 30 seconds

### steps 2:Tell the AI what you want in plain English

in dialog box**Speak directly**,For example:

| what you said | AI What will actually be screened?(automatic inference) |
|---------|------------------------|
| "Bank stocks with low valuations and high dividends" | banking industry + **PE less than 10** + **The dividend yield is greater than 4%** |
| "A leader in the new energy industry with a market value greater than 50 billion" | New energy industry + **Total market capitalization > 500 billion** + Industry leading stocks |
| "Technology stocks that have surged recently" | technology industry + **Top gainers in the past 20 days** |
| "Growth stocks with market capitalization of RMB 10-50 billion and ROE greater than 15%" | **Mid game** Market value + **ROE > 15%** |
| "The pharmaceutical white horse heavily stocked by institutions" | Pharmaceutical industry + **Institutional holdings are high** The faucet |

> 💡 **I can't understand the PE, ROE, and dividend yield in the table?** don't worry,These are all AI helps you"Translation"of,you**Just speak plainly**. 
> 💡 **Can spoken expressions be understood by AI??** Can. AI will intelligently infer what you mean(For example"Rising sharply"= Top gainers in the past 20 days,"white horse"= Industry leader + Good fundamentals). If the inference is biased,The next step can be corrected.

Send method:Press after inputting `Ctrl+Enter`,or**Just click on the right side of the input box"send"button**(Paper airplane icon,Usually in the lower right corner). 

### steps 3:AI retell + you confirm(Very critical!)

AI After receiving your request,Will**Let me repeat it first**Let you confirm:

> **AI**: "I understand you want to filter:**banking industry,PE<10, dividend yield>4%**. This will filter out approximately X stocks. Do you want to continue??"

At this time**There will be two buttons in the center of the screen**:
- **"Confirm filter"** button(blue home button,Below the AI reply):Click this if you are satisfied,AI Start getting results
- **"Modify requirements"** button(Gray secondary button,next to):If you want to adjust, click this,Add in input box,For example"Add another one with a total market value greater than 100 billion"

> ⚠️ **If the AI retells it incorrectly,Don't order it"Confirm"!** Supplement or correct directly in the input box,For example"No X,what i want is Y",AI Understanding will be revised based on context.

### steps 4:View stock cards(result)

After confirmation,AI Will come out**Stock card list**(Vertical,1 card per row),Each card shows:

```
┌─────────────────────────────┐
│ ☑ 600519 Kweichow Moutai            │
│ current price: 1680.50  +1.2%      │
│ PE: 28  PB: 9.5  dividend yield: 1.5%│
│ Total market capitalization: 2.1 trillions             │
│ Industry: Liquor                │
└─────────────────────────────┘
```

Key information for each card:
- **Stock code + Name**(top)
- **current price + Increase or decrease**(🔴 Red means rising,🟢 Green means down,This is the color habit of the A-share market)
- **key indicators**:PE, PB, Dividend yield, total market capitalization
- **Industry**

**Check the box in the upper right corner of the card**(☐)Join"List to be analyzed in batches",The selected card border will turn blue.

> 💡 **How to read these numbers?**(For novice users)
>
> | indicator | meaning | rough reference |
> |------|------|---------|
> | **PE**(P/E ratio) | Investment return period(Theoretical value),PE=Stock price/annual profit | <15 Underestimating,15-30 reasonable,>30 Expensive |
> | **PB**(price to book ratio) | The multiple of stock price to net assets per share | <1 Break the net,1-3 reasonable,>5 Expensive |
> | **dividend yield** | Annual dividends as a percentage of stock price | >3% high dividends,1-3% medium,<1% lower |
> | **Total market capitalization** | total company value | >1000 100 million large-cap stocks,200-1000 100 million mid-cap,<200 100 million small cap |
>
> ⚠️ **Note**:these numbers**It doesn't make much sense when viewed alone.**,want**Combine industries**and**Other indicators**Comprehensive judgment. Such as bank stocks PE=6 is the norm,technology stocks PE=30 Probably cheap.

### steps 5:Send batch analysis with one click

- in the results area**above**(Top of page)Find"**Batch analysis(N)**"button(N It's the number you checked)
- after click,system**Automatically jump to**"Batch Analysis page,The stock code has been filled in
- Set parameters on the batch analysis page:
  - **Analysis depth**(Top drop down):Recommended"**🎯 3 Level - Standard Analysis**"(6-10 minutes/only,Balance speed and quality)
  - **Analyst Team**(checkbox below):**Keep default checked**That's it,The system has selected 2 core analysts:
    - 📈 **market analyst**:Technical aspects, price trends, moving averages/MACD/RSI
    - 💰 **fundamental analyst**:Financial data, valuations, business models
  - **Submit task**:at the bottom of the page"**Submit analysis**"button(big blue button,lower left corner)
- post-submission system**Automatically jump to**""Task Center" and other results
  - 💡 **mission center location**:sidebar"my task"→"mission center"
  - When the task is completed there will be **Site notification**(Bell in the upper right corner)+ Email notification(If set)

## 🆚 "Smart filtering" vs "Advanced mode" How to choose

If natural language filtering**Not accurate enough**Or you want to do refined screening,can switch to"Advanced mode":

| Dimensions | Smart filtering(natural language) | Advanced mode(conditional form) |
|------|------------------|------------------|
| entrance | Default Tab | Need to switch manually |
| Operation mode | one sentence conversation | Form filling conditions |
| Suitable for whom | **Newbie/don't know the field name** | Experienced/want precise control |
| speed | AI Takes 5-10 seconds to understand | **Instant** |
| Accuracy | medium(AI inference) | **high**(exact field) |
| complex conditions | difficult to express | **Support nesting AND/OR** |

**Practical suggestions**:
- **First time use / don't know the field name** → Use smart filtering
- **clearly know to PE<15 + PB<2 +dividend yield>3%** → Use advanced mode to be more direct
- **Both can be combined**:Use smart filtering to narrow down the scope first,Then use advanced mode to refine

> 💡 **Two-tier structure of advanced mode**:
> - **Common conditions**:8 common fields displayed by default on the page(Stock code/name, industry classification, market type, market capitalization range, price-earnings ratio(PE), price to book ratio(PB), Price rise and fall, trading volume),Covers 80% of scenes
> - **Advanced fields**:Not shown by default,Need from"Add field"Pull down to automatically check(Applicable to"I want to add more detailed conditions",Such as ROE, dividend rate, revenue growth, gross profit margin, etc.)
>
> 📌 **Specific operations of advanced mode**See details [Lesson 2:Batch analysis](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-01-discover/lesson-02-batch-analysis.md) of"Advanced mode"Chapter.

## 📊 Conversation history:Go back to previous filters at any time

left side"Filter history"Panel records all your screening sessions,will not be lost:

- **continue the conversation**:Click on a conversation in history,Can review/continue conversation
- **New session**:point"New"button(Usually at the top of the history list)Start a new session
- **Delete a single item**:Hover the mouse over a piece of history,Appears on the right"Delete"icon
- **Clear current session**:in**The upper right corner of the current session window**Yes"Clear"button(trash can icon)

## 💬 Multiple rounds of dialogue:Ask questions like chatting

Smart filtering support**Multiple rounds of dialogue**,No need to re-describe each time:

```
Round 1:
you: bank stocks
AI: retell → banking industry,about 30

Round 2:
you: Add one more ROE>15%
AI: retell → banking industry + ROE>15%,about 12

Round 3:
you: Exclude sub-prime banks
AI: retell → banking industry + ROE>15% + Listed > 3 year,about 8
```

AI will be based on**contextual questioning**,You just need to say the increment condition,No need to repeat.

> ⚠️ **When do you need to create a new session??**
> - switch**completely different needs**(For example"bank stocks" → "New energy stocks")time,It is recommended to create a new session,Avoid contextual distractions
> - same filter**More than 10 rounds of questioning**time,It is recommended to create a new session(AI possible"forget"early conditions)

## ⚠️ What to do in case of abnormal situation?

### situation 1:Filter out 0 stocks

- **Reason**:The conditions are too strict,For example, requesting at the same time"PE<5 + bank stocks + Total market capitalization>1 trillions"
- **solve**:
  1. Say in the input box"Relax PE restrictions to 10"
  2. or"Market capitalization relaxed to 500 billion"
  3. AI Will adjust based on context

### situation 2:Sieve out 1000+ only stocks

- **Reason**:Condition is too broad,For example"technology stocks"(The industry is too big)
- **solve**:
  1. Add more detailed conditions:"Subdivided into semiconductors""Market value 20-100 billion""ROE>10%"
  2. or cut to"Advanced mode"Refine with exact fields
- **Not recommended**Send batch analysis directly(Over 1000 the analysis will be very slow)

### situation 3:AI Wrong retelling

- **Don't click"Confirm filter"**
- Correct in input box:"No X,what i want is Y"
- AI Will be corrected based on context,No need to start over

### situation 4:Page loads slowly/turns around for a long time

- Smart filtering takes 1-2 seconds to load for the first time(normal)
- if**more than 30 seconds**Still spinning,refresh page(F5)Try again
- Still not working,Check the upper right corner of the browser to see if there is"network error"Tips

## 📌 What you can do with filter results?(Panorama)

After screening out stocks,you can:

| Purpose | How to operate | Applicable scenarios |
|------|---------|---------|
| **Batch analysis** | point"Batch analysis(N)"button | 5-10 only stocks,Need in-depth research |
| **Add to watchlist** | upper right corner of card⭐icon | Long term tracking,No rush to study |
| **Add optional stocks** | Right click on card→"Add to your choice" | Common stocks,Convenient and quick viewing |
| **View individual stock details** | Click card stock name | Quickly view K-line, news, announcements |
| **Export Excel** | Upper right corner of results area"Export"button | Offline analysis and note-taking |
| **Write screening notes** | History session→point"Remarks"icon | Record filtering logic,Reuse later |

> 💡 **Beginner advice**:Top 3 uses(Batch analysis/focus/select)That's enough,Other advanced usages will be discussed after you become proficient.

## 🛠️ Practical operations(Follow along,Once done, master it)

**target**:Use smart screening to find 3-5 new energy stocks worth researching

1. Click the "Stock Screening" menu on the sidebar,Enter by default"Smart filtering" Tab
2. input:**"New energy industry,The total market value is greater than 50 billion,ROE greater than 10%,The increase in the past year was lower than 20%"**
   - 💡 explain:`Total market capitalization > 500 billion` Exclude small companies;`ROE > 10%` Choose one with strong profitability;`Increase in the past year < 20%` Exclude those that have risen very high(Chasing high is risky)
3. AI Restatement needs,View results after confirmation(You should sift out 10-30)
4. switch to"Advanced mode" Tab,look"Common conditions"What conditions are automatically filled in for the district?;You can also order"Add field"supplement"dividend yield"and other advanced conditions
5. Check 3-5 items,Click at the top of the page"**Batch analysis(N)**"button
6. On the batch analysis page:
   - **Analysis depth** set to"**🎯 3 Level - Standard Analysis**"
   - **Analyst Team** keep default(The system will automatically select the fundamentals + market)
   - Click on the lower left corner of the page"**Submit analysis**"button
7. The system automatically jumps to "Task Center",Wait for the task to be completed(Site notification + Email reminder)

**Finish this assignment**,You have mastered the core of v3.0"natural language→stock pool→Batch research"Full link.

## ✅ Complete checklist

After completing the practical exercise,Control check:

- [ ] Ability to enter the "Stock Screening" page from the sidebar
- [ ] Know that the default is"Smart filtering" Tab
- [ ] Able to enter screening requirements in plain English
- [ ] See AI retell and understand
- [ ] meeting point"Confirm filter"Out the results
- [ ] See stock cards and be able to check them
- [ ] Can order"Batch analysis(N)"Jump to batch analysis page
- [ ] Can be selected on the batch analysis page"🎯 3 Level - Standard Analysis"
- [ ] know"Analyst Team"Fundamentals included by default + market
- [ ] Able to submit tasks and jump to the task center

**Tick them all?** Congratulations,You have mastered the core usage of v3.0 filtering function!

## ❓ FAQ

**Q:I never learned stock terminology,Can it be used directly??**
A: Absolutely.**Smart filtering is designed for people who don't understand terminology**. you just say"Bank stocks with low valuations and high dividends",AI We will help you translate it into professional conditions such as PE and dividend rate. if you want to learn,all"AI What will actually be screened?"That column will display professional terms,The more you read, the more you will understand.

**Q:AI Wrong retelling,How to correct?**
A: **Don't click"Confirm filter"!** Supplement or correct directly in the input box,For example"What I said is not X,what i want is Y"or"Add one more ROE>15%". AI Will revise understanding based on context,No need to start over.

**Q:What conditions are supported??**
A: A Common financial indicators for stocks(PE/PB/ROE/Dividend rate/revenue growth rate/gross profit margin, etc.), Technical indicators, industries, market value ranges, price increases and decreases, etc. 100+ fields. The specific fields are in"Advanced mode → Add field"You can see it below.**Novice users generally don't need these**,5 categories of smart filtering(Industry/Valuation/Market Capitalization/Rise and Fall/Finance)It's enough.

**Q:How many stocks can be screened at one time??**
A: no hard limit,But**It is recommended to use smart screening to narrow down to 100-500 animals first.**,reuse"Advanced mode"Refinement to 50-100 pieces,Send for batch analysis.**Batch analysis of more than 1000 items will be slow**,And you don't have that much energy to read so many reports.

**Q:"Rising sharply", "white horse"AI can really understand this colloquial word?**
A: can,But there is a certain degree of subjectivity. AI infers based on common understanding:
- "Rising sharply" → Top gainers in the past 20 days(before 10%)
- "white horse" → Industry leader + Good fundamentals(High ROE, stable growth)
- "Unpopular" → Low attention and few institutional holdings
- "Monster stocks" → Short-term surges and huge fluctuations

If the inference is biased,**Corrected during AI retelling**That's it.

**Q:How long are filter results saved??Will it be lost??**
A: Smart filtered conversation history is saved under your account,will not be lost(Unless you delete it manually). Advanced mode conditions**Do not save automatically**,I need some from you"save"to retain(You can choose to load it the next time you enter). 

**Q:"Advanced mode"and"Smart filtering"Can they be used at the same time??**
A: OK!Common usage:
1. First use intelligent filtering to describe the general direction(For example"low valuation bank")
2. Switch to advanced mode,I saw AI fill it in for you."Common conditions"District
3. Manually fine-tune some values(For example, put PE<10 Change to PE<15)
4. point"Add field",supplement"dividend yield>3%"and other advanced conditions
5. point"Start filtering",Out the results

In this way, there is intelligent inference of AI,Again you have precise control.

**Q:There is a difference between the screening results and the actual market conditions.,Is it normal??**
A: normal. Filtering is based on**historical financial data**and**Latest Quotes**(T-1 daily close)of,It is normal for real-time market conditions to change. If you need the latest data,You can click before filtering"Refresh data"button.

**Q:Can I filter ETF funds??**
A: Yes. Say it directly when filtering intelligently"low rates ETF""Shanghai and Shenzhen 300ETF""Industry ETF"Wait,AI Will switch to ETF pool. In advanced mode"market type"Drop down selection"ETF"That's it.

## 📚 Further reading

- [Lesson 2:Batch analysis——Shrunk from 500 to 50](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-01-discover/lesson-02-batch-analysis.md)
- [Lesson 3:An Introduction to Single Stock Research——50 Just pick 5](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-01-discover/lesson-03-single-analysis-basic.md)


