import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src', 'multi_bot'))

from dynamic_grid import DynamicGridCalculator

def test_atr_calculation():
    """Test ATR calculation with sample data"""
    print("=== Testing ATR Calculation ===")
    
    # Create dynamic grid calculator
    dg = DynamicGridCalculator(
        symbol="BTCUSDT",
        atr_period=14,
        base_grid_spacing=0.002
    )
    
    # Sample OHLC data (High, Low, Close)
    sample_data = [
        (50000, 49000, 49500),  # Day 1
        (49800, 48500, 49200),  # Day 2  
        (49500, 48800, 49000),  # Day 3
        (49200, 48000, 48500),  # Day 4
        (48800, 47500, 48000),  # Day 5
        (48200, 47000, 47800),  # Day 6
        (48000, 46800, 47500),  # Day 7
        (47800, 46500, 47000),  # Day 8
        (47200, 46000, 46800),  # Day 9
        (47000, 45800, 46500),  # Day 10
        (46800, 45500, 46200),  # Day 11
        (46500, 45200, 45800),  # Day 12
        (46000, 44800, 45500),  # Day 13
        (45800, 44500, 45200),  # Day 14
        (45500, 44200, 44800),  # Day 15 (now we have 14 periods)
    ]
    
    for i, (high, low, close) in enumerate(sample_data):
        dg.update_price_data(high, low, close)
        if i >= 13:  # After 14 periods
            print(f"Day {i+1}: ATR = {dg.current_atr:.2f}, Volatility Ratio = {dg.current_volatility_ratio:.4f}")
    
    return dg

def test_bollinger_bands():
    """Test Bollinger Bands calculation"""
    print("\n=== Testing Bollinger Bands ===")
    
    dg = DynamicGridCalculator(
        symbol="BTCUSDT",
        bollinger_period=10,
        base_grid_spacing=0.002
    )
    
    # Sample price data
    prices = [45000, 45200, 44800, 45500, 45800, 46000, 45700, 45900, 46200, 46500, 46800]
    
    for i, price in enumerate(prices):
        dg.update_price_data(price, price * 0.99, price)  # Using close as high/low approximation
        if i >= 9:  # After 10 periods
            bb = dg.bollinger_bands
            if bb:
                print(f"Day {i+1}: Upper = {bb['upper']:.2f}, Middle = {bb['middle']:.2f}, Lower = {bb['lower']:.2f}")
                print(f"         Bandwidth = {bb['bandwidth']:.4f}")
    
    return dg

def test_dynamic_grid_params():
    """Test dynamic grid parameter calculation"""
    print("\n=== Testing Dynamic Grid Parameters ===")
    
    dg = test_atr_calculation()  # Use data from ATR test
    
    # Test different volatility scenarios
    scenarios = [
        ("Low Volatility", 0.008),
        ("Normal Volatility", 0.025),
        ("High Volatility", 0.045),
        ("Very High Volatility", 0.06)
    ]
    
    for scenario_name, vol_ratio in scenarios:
        # Manually set volatility ratio for testing
        dg.current_volatility_ratio = vol_ratio
        dg.current_atr = vol_ratio * 45000  # Approximate ATR based on price
        
        params = dg.calculate_dynamic_grid_params()
        print(f"\n{scenario_name} (Ratio: {vol_ratio:.3f}):")
        print(f"  Grid Spacing: {params['grid_spacing']:.4f}")
        print(f"  Grid Levels: {params['grid_levels']}")
        print(f"  Adjustment Factor: {params['adjustment_factor']:.2f}")

def test_grid_generation():
    """Test grid level generation"""
    print("\n=== Testing Grid Level Generation ===")
    
    dg = DynamicGridCalculator(
        symbol="BTCUSDT",
        base_grid_spacing=0.002
    )
    
    # Set some volatility for testing
    dg.current_volatility_ratio = 0.025
    dg.current_atr = 1000
    
    current_price = 45000
    total_investment = 1000
    
    # Test different position biases
    biases = ['neutral', 'long', 'short']
    
    for bias in biases:
        print(f"\n{bias.capitalize()} Bias:")
        grids = dg.generate_grid_levels(current_price, total_investment, bias)
        
        buy_grids = [g for g in grids if g.side == 'buy']
        sell_grids = [g for g in grids if g.side == 'sell']
        
        print(f"  Total Grids: {len(grids)}")
        print(f"  Buy Grids: {len(buy_grids)}")
        print(f"  Sell Grids: {len(sell_grids)}")
        
        if grids:
            print(f"  Price Range: {min(g.price for g in grids):.2f} - {max(g.price for g in grids):.2f}")
            
            # Show first few buy and sell orders
            buy_grids_sorted = sorted(buy_grids, key=lambda x: x.price, reverse=True)[:3]
            sell_grids_sorted = sorted(sell_grids, key=lambda x: x.price)[:3]
            
            print("  Top Buy Orders:")
            for grid in buy_grids_sorted:
                print(f"    Price: {grid.price:.2f}, Qty: {grid.quantity:.4f}")
                
            print("  Top Sell Orders:")
            for grid in sell_grids_sorted:
                print(f"    Price: {grid.price:.2f}, Qty: {grid.quantity:.4f}")

def test_market_condition_detection():
    """Test market condition detection"""
    print("\n=== Testing Market Condition Detection ===")
    
    dg = DynamicGridCalculator(
        symbol="BTCUSDT",
        base_grid_spacing=0.002
    )
    
    # Simulate different market conditions
    scenarios = [
        ("Sideways Market", [45000] * 20, "Normal volatility, mid-range"),
        ("Volatile Market", [45000 + 1000 * np.sin(i/3) for i in range(20)], "High volatility"),
        ("Trending Up", [45000 + i * 100 for i in range(20)], "Low volatility, trend"),
        ("Trending Down", [45000 - i * 100 for i in range(20)], "Low volatility, trend")
    ]
    
    for scenario_name, prices, expected in scenarios:
        # Reset calculator
        dg = DynamicGridCalculator(symbol="BTCUSDT", base_grid_spacing=0.002)
        
        # Feed price data
        for price in prices:
            high = price * 1.01
            low = price * 0.99
            dg.update_price_data(high, low, price)
        
        condition = dg.get_market_condition()
        metrics = dg.get_volatility_metrics()
        
        print(f"\n{scenario_name}:")
        print(f"  Detected Condition: {condition}")
        print(f"  Expected: {expected}")
        print(f"  Volatility Ratio: {metrics.get('volatility_ratio', 'N/A'):.4f}")
        print(f"  Grid Spacing: {metrics.get('grid_spacing', 'N/A'):.4f}")
        print(f"  Grid Levels: {metrics.get('grid_levels', 'N/A')}")

def test_grid_adjustment_strategy():
    """Test grid adjustment strategy"""
    print("\n=== Testing Grid Adjustment Strategy ===")
    
    dg = DynamicGridCalculator(
        symbol="BTCUSDT", 
        base_grid_spacing=0.002
    )
    dg.update_interval = 1  # 1 second for testing
    
    # Set initial state
    current_price = 45000
    
    # Generate initial grids
    initial_grids = dg.generate_grid_levels(current_price, 1000)
    print(f"Initial Grid Spacing: {dg.grid_spacing:.4f}")
    print(f"Initial Grid Levels: {dg.grid_levels_count}")
    
    # Simulate volatility change
    import time
    time.sleep(2)  # Wait for time-based check
    
    # Inject high volatility data
    for i in range(15):
        high = current_price * (1.05 + 0.02 * np.random.random())
        low = current_price * (0.95 - 0.02 * np.random.random())
        close = current_price * (1 + 0.03 * np.random.randn())
        dg.update_price_data(high, low, close)
    
    strategy = dg.get_grid_adjustment_strategy(current_price)
    print(f"\nAfter Volatility Change:")
    print(f"  Strategy Action: {strategy['action']}")
    
    if strategy['action'] == 'adjust':
        print(f"  New Spacing: {strategy['new_spacing']:.4f}")
        print(f"  New Levels: {strategy['new_levels']}")
        print(f"  Volatility Ratio: {strategy.get('volatility_ratio', 'N/A'):.4f}")

def run_all_tests():
    """Run all dynamic grid tests"""
    print("Dynamic Grid Trading System - Test Suite")
    print("=" * 50)
    
    try:
        test_atr_calculation()
        test_bollinger_bands()
        test_dynamic_grid_params()
        test_grid_generation()
        test_market_condition_detection()
        test_grid_adjustment_strategy()
        
        print("\n" + "=" * 50)
        print("All tests completed successfully!")
        
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_all_tests()