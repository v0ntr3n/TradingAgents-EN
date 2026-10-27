---
name: stock-cyq-analyzer
description: >
  Chip distribution analysis tool (CYQ - Chip Distribution).
  Calculate professional indicators such as profit ratio, main cost area, and chip concentration based on volume and price data.
  Using the triangular distribution model, all A-share stocks are supported.
  Use when: User mentioned"Chip distribution", "Chip analysis", "CYQ", "Take profit", "Main cost", "Chip concentration", "90%cost". 
  NOT for: Recommend buying and selling opportunities, predict stock price trends, and give investment advice.
---

# CYQ Chip distribution analysis tool

## Skills Overview

This tool calculates the chip distribution (CYQ) of a stock, uses a triangular distribution model based on volume and price data, and outputs professional chip analysis indicators and visual charts.

### Core algorithm
- Typical prices:`(Open + High + Low + Close) / 4`
- Distribution assumptions: Triangular distribution (low, high, typical price)
- Historical decay: linear decay according to turnover rate `(1 - turnover)`
- Price step size: 0.1 yuan

### Output indicators
| indicator | Description |
|------|------|
| Profit ratio | The proportion of chips below the current price |
| average cost | Average cost price of position holders |
| chip peak | The price with the most intensive chips |
| 90%Chip concentration | 90%The width of the price range where the chips are located |
| main cost area | The 20% range with the most intensive chips |

## Preconditions

### Install dependencies
Before first use, install Python dependencies (versions are specified in requirements.txt):

```bash
pip3 install -r requirements.txt
```

### How to use

```bash
cd scripts
python3 cyq_analyzer.py <Stock code>
```

Example:

```bash
python3 cyq_analyzer.py 000547
```

The output is in standard JSON format and contains chip analysis indicators and chart paths.
