# Lesson 2:Batch analysis——Shrunk from 500 to 50

> **Class hours**: 25 minutes | **difficulty**: ⭐⭐ Advanced | **prefix**: Lesson 1(stock screen)

> ⚠️ **Risk warning**:The content of this course is only for teaching platform functions.,AI The research report output does not constitute investment advice.,The final decision is yours.

## 🎯 What can you do after studying?

- One-time submission **Maximum 10** A stock analysis
- Choose 5 depths of analysis(1 Level 2 quick analysis / Level 2 basic analysis / Level 3 standard analysis / Level 4 in-depth analysis / Level 5 comprehensive analysis)
- Check 7 analysts(Market, fundamentals, news, social media, market, sectors,1 more ETF analyst when choosing an ETF)
- Track progress in the Task Center menu
- View the comparison report in the "Research Report" menu

## 📍 entrance

- **sidebar**: stock analysis → Batch research
- **Jump from filter**: At the Filter Results point in Lesson 1"Batch analysis"Automatic jump

> ⚠️ **v3.0 Important changes**:The batch analysis page is"Advanced"Function,Top has"⚠️ Important tips:This analysis is only used for learning, research and public information compilation,No guidance on individual stock trading is provided"Risk Disclaimer.

## 🖱️ Operation steps

### steps 1:Enter the batch analysis page

1. Click on the sidebar"stock analysis → Batch research"
2. After entering, you will see three areas:**stock list**(on), **Analysis configuration**(left), **Advanced configuration**(right)

### steps 2:Choose a market(Default A shares)

- in"stock list"top of card,**The default is A-share market**(🇨🇳)
- You can also switch to **ETF fund**(📈),code example:510050, 159919
- **No Hong Kong/US stock options**——v3.0 The platform only supports A shares and ETF

### steps 3:Enter stock code

in text box**One per row** or **comma/space separated** All is OK,For example:

```
600519
000858, 300750
601919 000333
```

Supported formats:
- numeric code:`600519`
- Multiple codes can be separated by newlines, commas, or spaces.
- The front end will automatically parse,Invalid code will be in"Invalid code prompt"listed in

**Important limitations**:
- ⚠️ **Maximum of 10 stocks at a time**


> 💡 **Practical skills**:If you want to analyze 50,Requires 5 submissions(50/10). You can use Lesson 1 first"Advanced mode"Filter to 50 by condition,Then send them in batches for batch analysis.

### steps 4:Select analysis depth(5 level optional)

In the page"Analysis depth"The actual display names of the drop-down box are these 5:

| level | Page display name | Time consuming/only | Applicable scenarios |
|------|------|---------|---------|
| 1 | ⚡ **1 Level - Quick Analysis** | 6-10 minutes | Bulk pre-screening,Fast first and then deep |
| 2 | 📈 **2 Level - Basic Analysis** | 7-12 minutes | preliminary research |
| 3 | 🎯 **3 Level - Standard Analysis**(Recommended) | 8-15 minutes | Daily research main force |
| 4 | 🔍 **4 Level - In-Depth Analysis** | 10-20 minutes | before important decisions |
| 5 | 🏆 **5 Level - Comprehensive Analysis** | 15-25 minutes | In-depth due diligence on key targets |

**Practical suggestions**:
- **first time** look at a stock → choose 3(Standard)
- **Already seen,Think about multiple perspectives** → choose 4-5
- **Large batch pre-screening** → choose 1-2

### steps 5:Select analysis process(Optional,if there is)

- The system will list all stock analysis workflows
- The system-preset workflow is selected by default
- Workflow determines"Which analysts to use and in what order"
- Lesson 26 of the course covers how to create custom workflows

> 💡 **most users**:Leave it alone,Just use the default workflow.

### steps 6:Choose an analyst team

**core distinction**:here"Analyst Team"Checked is**Input roles used for single analysis**. **Pay attention to the distinction**:
- Page"Analyst Team"Can be checked below:**Only 7 analysts**(A stock scene)
- But**You can actually see it in the report**research role,Also includes debaters, research integrators, risk assessors, etc.

**7 analysts in the tick box**(What users actually see):

| Classification | analyst(Page display name) | function |
|------|--------|------|
| **Individual stocks** | 📈 market analyst | technical aspect+Disk |
| | 💰 fundamental analyst | Finance+Valuation |
| | 📰 news analyst | real time news |
| | 💬 social media analyst | public opinion sentiment |
| **Macroscopic aspect** | 📊 Market Analyst | Market environment |
| | 🏭 Sector Analyst | Industry status |
| **ETF Proprietary**(Appears only when selecting ETF market) | ETF analyst | ETF Net worth, tracking error |

**Other research roles that actually appear in the report**(After selecting the analyst,The workflow will automatically run out):

| Report Tab name(What users see) | role | function |
|--------|------|------|
| 🐂 Optimistic Scenario Researcher | optimistic view research | Find evidence to support the rise |
| 🐻 Prudential Scenario Researcher | Careful perspective research | Find evidence to support decline/caution |
| ⚡ Highly Resilient Scenario Analyst | Highly Resilient Risk Perspective | aggressive risk research |
| 🛡️ Defense Scenario Analyst | Defense risk perspective | conservative risk research |
| ⚖️ Baseline Scenario Analyst | neutral risk perspective | objective risk study |
| 🔬 research integrator | Comprehensive integration | Integrate all research |
| 👔 risk assessor | risk research | risk research synthesis |

**Practical suggestions**:
- **newbie**:Check"market analyst+fundamental analyst"That's enough(The system checks these 2 by default)
- **Advanced**:put"Market Analyst+Sector Analyst"Also add,Look at the macro background
- **Bulk pre-screening**:Only tick"market analyst",run fast

### steps 7:Configure AI model(Advanced configuration on the right)

right side"🔧 Advanced configuration"The card has **ModelConfig** components:
- **Quickly analyze models**:For use in depth levels 1-2(Choose a cheap model,Such as qwen-plus)
- **Deep analysis model**:For use in depth levels 3-5(strong selection model,Such as qwen-max)
- The platform will press"Analysis depth"Automatically switch which model to use

> 💡 **JD Cloud users**:Limited model selection,Subject to what has been configured on the platform,No need to change manually.

### steps 8:Submit batch analysis

- point"Start batch analysis(N only)"button
- The system pops up a confirmation box:"Are you sure you want to submit the batch analysis task??market:A Share Quantity:N Only analysis engine:v2.0 engine"
- After confirmation,Task enqueue

**v2.0 engine**is the only engine currently available(Legacy engine is hidden). 

### steps 9:Track progress

After submission,The task will run in the background.**Note**:

| platform | Concurrency | Queuing instructions |
|------|---------|---------|
| **Jingdong cloud version** | single concurrency(1) | ⚠️ 10 Only tasks are executed serially,**Total time spent = 10 × Time-consuming alone** |
| **Standard Edition** | Depends on configuration | Look at the backend `queue_service` Configuration |

- Enter the "Task Center" menu to check the progress
- or at the bottom of the batch analysis page"recent analysis"List view
- Completed tasks will be displayed"completed",Failure display"failed"

### steps 10:View comparison report

After the task is completed,There are two ways to view:

1. Click the "Research Report" menu on the sidebar → See a list of all completed tasks
2. **single report**: Order something"View" → Enter the report details page,See all 12 subreports

**v3.0 Report actually contains 12 sub-reports Tab**(See Lesson 3 for details),The following are users**Report details page**inside**The actual tab name seen**:

| Report Tab name(What users see) | actual field key | stage |
|--------|--------|------|
| 📊 Market Analyst | index_report | Macro |
| 🏭 Sector Analyst | sector_report | Macro |
| 📈 market analyst | market_report | Individual Stocks-Technical Aspects |
| 💬 social media analyst | sentiment_report | Individual stocks-emotional aspect |
| 📰 news analyst | news_report | Individual stocks - news side |
| 💰 fundamental analyst | fundamentals_report | Individual Stocks-Fundamentals |
| 🐂 Optimistic Scenario Researcher | bull_researcher | Multi-scenario-Multiple |
| 🐻 Prudential Scenario Researcher | bear_researcher | Multi-scenario-null |
| ⚡ Highly Resilient Scenario Analyst | risky_analyst | risk debate |
| 🛡️ Defense Scenario Analyst | safe_analyst | risk debate |
| ⚖️ Baseline Scenario Analyst | neutral_analyst | risk debate |
| 👔 risk assessor | risk_management_decision | risk synthesis |
| 🧩 research integrator | trader_investment_plan | research integration |
| 🧾 Comprehensive research conclusion | final_trade_decision | final conclusion |

## ⚠️ v3.0 Important changes

- ✅ **v2.0 Engine unity**:Legacy engine is hidden,only keep v2.0(Workflow based)
- ✅ **Workflow optional**:User can select/create custom workflows(Lesson 26)
- ✅ **5 level analysis depth**:Expanded from Level 3 to Level 5(1 Level 2 quick analysis / Level 2 basic analysis / Level 3 standard analysis / Level 4 in-depth analysis / Level 5 comprehensive analysis)
- ⚠️ **Hard limit of 10 pieces at a time**:Backend / frontend two-factor authentication,cannot be bypassed
- ⚠️ **The platform only supports A shares and ETF**


## 🛠️ Practical operations

1. Click the "Batch Analysis" menu on the sidebar
2. Enter in the text box:`600519, 000858, 300750`(3 Only A-share white horse)
3. Analysis depth selection **3 Level - Standard Analysis**(Recommended)
4. Analyst check:📈 market analyst + 💰 fundamental analyst(Just the default 2)
5. right side"Advanced configuration"Use default model
6. point"Start batch analysis(3 only)"button
7. Check the progress in the "Task Center" menu
8. After completion,point"View report"See all 14 subreports Tab
9. Compare 3"Optimistic/cautious/neutral"decision making

**Finish this assignment**,You have mastered the complete process of batch research.

## ❓ FAQ

**Q:Why did I submit only 12,be prompted"Maximum 10"?**
A: Backend hard limit,Requires 2 submissions. The system is not designed"Automatic batching over 10"Function,Requires manual operation.

**Q:3 Is there a big difference between level 4 and level 4??**
A: 4 Level one more than level 3**Debate**——🐂 Optimistic scenario researcher and 🐻 Prudential Scenario Researchers will discuss each other's views for one more round,better research,Reporting is slower but more comprehensive. The researcher and report tabs for both levels of running are the same.,The difference lies in the number of debate rounds. If level 3 is enough,No need to go for level 4-5.

**Q:Task stuck in"running"Not moving anymore?**
A: JD Cloud version order concurrency,If there are tasks ahead, they will be queued. Check the "Task Center""queue status",See if there are any tasks ahead.

**Q:Task failed(failed)what to do?**
A: See the task details `error_message`. Common causes:Stock data not synced(Go to "Settings"→"System Management→"Synchronization of multiple data sources), Token exhausted(Go to the Token Usage page in the "Research Report" menu to check the usage.). 

**Q:Is the report format for batch analysis the same as for single stock studies??**
A: yes,Exactly the same. All `analysis_reports` collection,There are 12 sub-report structures in total.

**Q:Can I use ETF funds to make batches??**
A: OK,in"market"Drop down selection ETF,Then enter the ETF symbol(Such as 510050). 

## 📚 Further reading

- [Lesson 1:stock screen](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-01-discover/lesson-01-stock-screening.md)
- [Lesson 3:An Introduction to Single Stock Research](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-01-discover/lesson-03-single-analysis-basic.md)
- [Lesson 9:timing analysis + Track the rhythm](file:///c:/TradingAgentsCN/docs/07-courses/v3.0/phase-02-track/lesson-09-scheduled-track-rhythm.md) - solve"Manually resubmit every day"question
