/**
 * Trading plan template configuration
 */

export interface TradingSystemTemplate {
  id: string
  name: string
  description: string
  style: 'short_term' | 'medium_term' | 'long_term'
  risk_profile: 'conservative' | 'balanced' | 'aggressive'
  data: {
    stock_selection: any
    timing: any
    position: any
    holding: any
    risk_management: any
    review: any
    discipline: any
  }
}

export const tradingSystemTemplates: TradingSystemTemplate[] = [
  {
    id: 'short_term_trend',
    name: 'Short term trend following system',
    description: 'Based on technical analysis, capturing short-term trend opportunities is suitable for investors who have time to keep an eye on the market.',
    style: 'short_term',
    risk_profile: 'aggressive',
    data: {
      stock_selection: {
        must_have: [
          { rule: 'Market value > 50 billion', description: 'Avoid liquidity risks in small-cap stocks' },
          { rule: 'Circulation plate > 10 billion', description: 'Ensure adequate liquidity' },
          { rule: 'Average transaction volume in the past 3 days > 1 billion', description: 'Activity requirements' },
          { rule: 'The stock price is above the 20-day moving average', description: 'Trending up' },
          { rule: 'Increase in the past 5 days > 5%', description: 'There is upward momentum' }
        ],
        exclude: [
          { rule: 'ST stocks', description: 'Risk is too high' },
          { rule: 'Sub-new stocks (listed for less than 1 year)', description: 'Excessive fluctuations' },
          { rule: 'Continuous lower limit', description: 'Avoid catching flying knives' },
          { rule: 'There has been major bad news recently', description: 'Fundamentals deteriorate' }
        ]
      },
      timing: {
        entry_signals: [
          { signal: 'The market is in an upward trend (CSI 300 Index MA20 > MA60) ', description: 'Good market environment' },
          { signal: 'Stock price breaks through previous high', description: 'technological breakthrough' },
          { signal: 'MACD golden fork', description: 'Momentum strengthens' },
          { signal: 'Trading volume increased by more than 50% compared with the average of the previous five days', description: 'Funding concerns' },
          { signal: 'Sunshine for 3 consecutive days', description: 'trend confirmation' }
        ]
      },
      position: {
        max_per_stock: 0.15,
        max_holdings: 8,
        min_holdings: 3
      },
      holding: {
        review_frequency: 'daily',
        add_conditions: [
          { condition: 'The stock price is more than 5% higher than the cost price', description: 'Add profit to position' },
          { condition: 'The upward trend is not broken', description: 'trend intact' }
        ],
        reduce_conditions: [
          { condition: 'Falling below the 5-day moving average', description: 'Short-term trend weakening' },
          { condition: 'Trading volume shrinks', description: 'kinetic energy failure' }
        ]
      },
      risk_management: {
        stop_loss: {
          type: 'percentage',
          percentage: 0.07,
          description: 'Fixed 7% stop loss'
        },
        take_profit: {
          type: 'trailing',
          description: 'Take profit if it falls below the 5-day moving average'
        }
      },
      review: {
        frequency: 'weekly',
        checklist: [
          'Check position performance',
          'Analyze buying and selling decisions',
          'Evaluate system execution',
          'Summarize experience and lessons'
        ]
      },
      discipline: {
        must_do: [
          { rule: 'Strictly enforce stop loss without any excuses', description: 'Protect principal' },
          { rule: 'All stock selection conditions must be checked before each trade', description: 'Ensure compliance with the system' },
          { rule: 'Timely review and summary after profit', description: 'Continuous improvement' },
          { rule: 'Trading log updated daily after market close', description: 'Complete records' }
        ],
        must_not: [
          { rule: 'Chasing the rise and killing the fall, emotional trading', description: 'stay rational' },
          { rule: 'A single stock with a heavy position exceeds 15%', description: 'Control risks' },
          { rule: 'Frequently trade the same stock within a day', description: 'Avoid overtrading' },
          { rule: 'Enter without stop loss', description: 'Must have protection' }
        ]
      }
    }
  },
  {
    id: 'medium_term_value',
    name: 'Mid-line value growth system',
    description: 'Combining fundamentals and technical aspects to find undervalued growth stocks, suitable for office workers',
    style: 'medium_term',
    risk_profile: 'balanced',
    data: {
      stock_selection: {
        must_have: [
          { rule: 'Market value > 100 billion', description: 'Mid- and large-cap stocks' },
          { rule: 'ROE > 15% (Average of the last 3 years)', description: 'Strong profitability' },
          { rule: 'revenue growth rate > 20% (Average of the last 3 years)', description: 'Good growth potential' },
          { rule: 'P/E ratio < Industry average', description: 'Reasonable valuation' },
          { rule: 'Debt ratio < 60%', description: 'financial health' }
        ],
        exclude: [
          { rule: 'ST stocks', description: 'Risk is too high' },
          { rule: 'Performance continues to decline', description: 'Fundamentals deteriorate' },
          { rule: 'There are major lawsuits or penalties', description: 'legal risks' },
          { rule: 'Major shareholders reduce holdings', description: 'lack of confidence' }
        ]
      },
      timing: {
        entry_signals: [
          { signal: 'The market is in a volatile or upward trend', description: 'market environment' },
          { signal: 'The stock price fell back to near the 60-day moving average', description: 'technical position' },
          { signal: 'MACD About to get a golden cross or just a golden cross', description: 'Momentum strengthens' },
          { signal: 'Major good news occurs (such as performance exceeding expectations)', description: 'catalyst' },
          { signal: 'institutional capital inflows', description: 'Funding Approval' }
        ]
      },
      position: {
        max_per_stock: 0.20,
        max_holdings: 6,
        min_holdings: 3
      },
      holding: {
        review_frequency: 'weekly',
        add_conditions: [],
        reduce_conditions: []
      },
      risk_management: {
        stop_loss: {
          type: 'percentage',
          percentage: 0.12,
          description: 'Fixed 12% stop loss'
        },
        take_profit: {
          type: 'scaled',
          description: 'If it goes up 30%, sell 1/3, if it goes up 50%, sell 1/3, and hold the rest.'
        }
      },
      review: {
        frequency: 'monthly',
        checklist: [
          'Reevaluate positions after quarterly earnings release',
          'Examine changes in industry and company fundamentals',
          'Assess valuation levels',
          'Summarize investment decisions'
        ]
      },
      discipline: {
        must_do: [
          { rule: 'Reevaluate positions after quarterly earnings release', description: 'Track fundamentals' },
          { rule: 'Strictly implement stop loss and take profit plans', description: 'Discipline enforcement' },
          { rule: 'Review regularly, at least once a month', description: 'Continuous improvement' },
          { rule: 'Keep positions diversified, no more than 3 industries', description: 'spread risk' }
        ],
        must_not: [
          { rule: 'Frequent trading due to short-term fluctuations', description: 'stay patient' },
          { rule: 'Buying without doing fundamental research', description: 'Must study' },
          { rule: 'Single stock with heavy position', description: 'Control risks' },
          { rule: 'Buy high', description: 'Waiting for a reasonable price' }
        ]
      }
    }
  },
  {
    id: 'long_term_value',
    name: 'Long-term value investment system',
    description: 'Focus on high-quality blue-chip stocks, hold them for a long time, share corporate growth, and are suitable for value investors',
    style: 'long_term',
    risk_profile: 'conservative',
    data: {
      stock_selection: {
        must_have: [
          { rule: 'Market value > 500 billion', description: 'blue chip market' },
          { rule: 'ROE > 15% (average over the past 5 years)', description: 'sustained profitability' },
          { rule: 'Profit growth for 5 consecutive years', description: 'Stable growth' },
          { rule: 'Industry leading position', description: 'competitive advantage' },
          { rule: 'dividend rate > 2%', description: 'shareholder returns' }
        ],
        exclude: [
          { rule: 'Cyclical industries (unless at the bottom)', description: 'Avoid cyclical fluctuations' },
          { rule: 'Highly indebted companies (debt ratio > 70%) ', description: 'financial risk' },
          { rule: 'Frequent changes in management', description: 'poor stability' },
          { rule: 'Main business is unclear', description: 'Unknown business model' }
        ]
      },
      timing: {
        entry_signals: [
          { signal: 'Shares are at historically low valuations (PE < historical average)', description: 'Reasonable valuation' },
          { signal: 'Irrational decline caused by systemic risks', description: 'market panic' },
          { signal: 'Major benefits (such as policy support, industry turning points)', description: 'Long term positive' },
          { signal: 'Increase in holdings by major shareholders or management', description: 'internal confidence' }
        ]
      },
      position: {
        max_per_stock: 0.30,
        max_holdings: 5,
        min_holdings: 2
      },
      holding: {
        review_frequency: 'monthly',
        add_conditions: [
          { condition: 'Valuations fall further', description: 'Opportunities to add positions' },
          { condition: 'Fundamentals continue to improve', description: 'boost confidence' }
        ],
        reduce_conditions: [
          { condition: 'overvalued', description: 'Take profits' },
          { condition: 'Fundamentals deteriorate', description: 'Stop loss promptly' }
        ]
      },
      risk_management: {
        stop_loss: {
          type: 'technical',
          description: 'Stop loss when it falls below the annual line and fundamentals deteriorate'
        },
        take_profit: {
          type: 'percentage',
          description: 'Sell when valuations are too high or fundamentals deteriorate'
        }
      },
      review: {
        frequency: 'quarterly',
        checklist: [
          'In-depth study of annual/quarterly reports of holding companies',
          'Pay attention to the company s major announcements',
          'Assess industry trends',
          'Check whether the investment logic has changed'
        ]
      },
      discipline: {
        must_do: [
          { rule: 'Conduct in-depth research on holding companies at least once a year', description: 'Understand investment targets' },
          { rule: 'Pay attention to the company s major announcements and financial reports', description: 'Track changes' },
          { rule: 'Be patient and not swayed by short-term fluctuations', description: 'long term thinking' },
          { rule: 'Rebalance regularly to maintain reasonable positions', description: 'Risk control' }
        ],
        must_not: [
          { rule: 'Frequent trading due to short-term rises and falls', description: 'long term holding' },
          { rule: 'Chasing hot spots and concept stocks', description: 'Stick to values' },
          { rule: 'Use leverage', description: 'Steady investment' },
          { rule: 'Buy without doing research', description: 'Must study in depth' }
        ]
      }
    }
  }
]

