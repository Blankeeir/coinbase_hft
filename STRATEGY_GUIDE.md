# Advanced HFT Strategy Guide

This document outlines the advanced strategy improvements implemented in the Coinbase International Exchange HFT Bot based on the research document provided.

## Core Strategy Components

The HFT bot implements a smart channel breakout strategy with an order book imbalance (OBI) machine learning factor. The strategy consists of the following components:

### 1. Channel Breakout

The channel breakout component detects when price escapes a rolling high/low band (Donchian Channel) over a configurable time window (default: 2 minutes). This provides the base signal for potential trend continuation.

```python
# Simplified channel breakout logic
upper_channel = max(high_prices[-window:])
lower_channel = min(low_prices[-window:])

if current_price > upper_channel:
    # Potential long signal
    return "BUY"
elif current_price < lower_channel:
    # Potential short signal
    return "SELL"
```

### 2. Order Book Imbalance (OBI)

The OBI factor measures the imbalance between bid and ask liquidity in the order book:

```
OBI = (sum(bid_sizes) - sum(ask_sizes)) / (sum(bid_sizes) + sum(ask_sizes))
```

A positive OBI indicates more buying pressure, while a negative OBI indicates more selling pressure. This helps filter out false breakout signals.

### 3. Machine Learning Factor

The strategy uses an SGDClassifier model to predict the direction of price movement based on features including:

- Order book imbalance (OBI)
- Short-term volatility
- Trade imbalance
- VWAP distance
- Recent price returns

The model is trained incrementally on live data, allowing it to adapt to changing market conditions.

## Advanced Strategy Improvements

Based on the research document, the following advanced improvements have been implemented:

### 1. Hawkes Process Intensity

The strategy now incorporates Hawkes process intensity to model the self-exciting nature of order flow. This helps predict future order flow based on recent order arrivals.

```python
# Hawkes process intensity calculation
def calculate_hawkes_intensity(events, decay_factor=0.1, time_window=60):
    current_time = time.time()
    intensity = 0.0
    
    for event_time in events:
        time_diff = current_time - event_time
        if time_diff <= time_window:
            intensity += np.exp(-decay_factor * time_diff)
    
    return intensity
```

This feature improves prediction accuracy by capturing the clustering behavior of market orders.

### 2. Enhanced Volatility Estimation

The strategy now uses a more sophisticated volatility estimation method that combines EWMA (Exponentially Weighted Moving Average) with jump detection:

```python
# Enhanced volatility estimation
def calculate_enhanced_volatility(returns, alpha=0.94, jump_threshold=3.0):
    ewma_var = 0.0
    for ret in returns:
        if abs(ret) > jump_threshold * np.sqrt(ewma_var):
            # Jump detected, reduce impact
            adjusted_ret = np.sign(ret) * jump_threshold * np.sqrt(ewma_var)
        else:
            adjusted_ret = ret
        
        ewma_var = alpha * ewma_var + (1 - alpha) * adjusted_ret**2
    
    return np.sqrt(ewma_var)
```

This approach provides more stable volatility estimates during periods of market stress.

### 3. Trade Imbalance Factor

The strategy now includes a trade imbalance factor that measures the net buying/selling pressure from executed trades:

```python
# Trade imbalance calculation
def calculate_trade_imbalance(trades, volume_weighted=True):
    buy_volume = sum(trade["quantity"] for trade in trades if trade["side"] == "BUY")
    sell_volume = sum(trade["quantity"] for trade in trades if trade["side"] == "SELL")
    
    total_volume = buy_volume + sell_volume
    if total_volume == 0:
        return 0.0
    
    return (buy_volume - sell_volume) / total_volume
```

This feature helps identify momentum in the market that may not be visible in the order book.

### 4. VWAP Distance

The strategy now calculates the distance of the current price from the Volume Weighted Average Price (VWAP):

```python
# VWAP distance calculation
def calculate_vwap_distance(trades, current_price):
    total_volume = sum(trade["quantity"] for trade in trades)
    if total_volume == 0:
        return 0.0
    
    vwap = sum(trade["price"] * trade["quantity"] for trade in trades) / total_volume
    
    return (current_price - vwap) / vwap  # Normalized distance
```

This feature helps identify potential mean reversion opportunities.

### 5. Probabilistic Signal Generation

The strategy now uses a probabilistic approach to signal generation, considering both the strength of the breakout and the confidence of the ML model:

```python
# Probabilistic signal generation
def generate_signal(breakout_signal, ml_probability, threshold=0.65):
    if breakout_signal == "BUY" and ml_probability > threshold:
        return "BUY", ml_probability
    elif breakout_signal == "SELL" and ml_probability < (1 - threshold):
        return "SELL", ml_probability
    else:
        return "NEUTRAL", ml_probability
```

This approach reduces false signals and improves the risk-adjusted return of the strategy.

## Performance Metrics

The strategy tracks the following performance metrics:

1. **Win Rate**: Percentage of profitable trades
2. **Profit Factor**: Gross profits divided by gross losses
3. **Sharpe Ratio**: Risk-adjusted return measure
4. **Maximum Drawdown**: Largest peak-to-trough decline
5. **Average Holding Time**: Average duration of positions

These metrics are logged and can be used to evaluate and optimize the strategy.

## Risk Management

The strategy includes the following risk management features:

1. **Position Limits**: Maximum position size per symbol
2. **Notional Value Limits**: Maximum notional value of positions
3. **Daily Loss Limits**: Maximum allowed daily loss
4. **Stop Loss**: Automatic position closure on adverse price movement
5. **Take Profit**: Automatic position closure on favorable price movement

These risk management features help protect capital during adverse market conditions.

## Further Improvements

Potential areas for further improvement include:

1. **Deep Learning Models**: Implementing more sophisticated neural network models for prediction
2. **Reinforcement Learning**: Using RL to optimize execution strategies
3. **Adaptive Parameters**: Dynamically adjusting strategy parameters based on market conditions
4. **Multi-Asset Strategies**: Extending the strategy to trade correlated assets
5. **Alternative Data**: Incorporating news sentiment and other alternative data sources

## References

1. Cartea, Á., Donnelly, R., & Jaimungal, S. (2018). Enhancing trading strategies with order book signals.
2. Cont, R., Kukanov, A., & Stoikov, S. (2014). The price impact of order book events.
3. Toke, I. M., & Pomponio, F. (2012). Modelling trades-through in a limit order book using Hawkes processes.
4. Abergel, F., & Jedidi, A. (2013). A mathematical approach to order book modeling.
5. Lehalle, C. A., & Laruelle, S. (2018). Market microstructure in practice.
