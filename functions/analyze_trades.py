import os
import pandas as pd
from datetime import datetime
import pytz
import logging
from pathlib import Path
from functions.manage_authentication import get_authenticated_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_trade_info(order):
    """Extract relevant trade information from an order and its child strategies"""
    trades = []
    et_tz = pytz.timezone('US/Eastern')
    
    # Function to process a single order
    def process_single_order(order_data):
        symbol = order_data['orderLegCollection'][0]['instrument']['symbol']
        instruction = order_data['orderLegCollection'][0]['instruction']
        quantity = order_data['quantity']
        
        # Get execution details
        execution = next((activity for activity in order_data['orderActivityCollection'] 
                         if activity['activityType'] == 'EXECUTION' and 
                         activity['executionType'] == 'FILL'), None)
        
        if not execution:
            return None
            
        # Get execution leg details
        exec_leg = execution['executionLegs'][0]
        price = exec_leg['price']
        time = datetime.fromisoformat(exec_leg['time'].replace('Z', '+00:00')).astimezone(et_tz)
        
        return {
            'Date': time,
            'Symbol': symbol,
            'Side': instruction,
            'Quantity': quantity,
            'Price': price,
            'Total Value': quantity * price
        }
    
    # Process main order
    main_trade = process_single_order(order)
    if main_trade:
        trades.append(main_trade)
    
    # Process child strategies (OCO orders)
    if 'childOrderStrategies' in order:
        for child_strategy in order['childOrderStrategies']:
            if 'childOrderStrategies' in child_strategy:
                for grandchild in child_strategy['childOrderStrategies']:
                    if grandchild['status'] == 'FILLED':
                        child_trade = process_single_order(grandchild)
                        if child_trade:
                            trades.append(child_trade)
    
    return trades

def get_todays_trades(client):
    """Get and analyze today's trades"""
    try:
        
        # Setup timezone and dates
        et_tz = pytz.timezone('US/Eastern')
        today = datetime.now(et_tz)
        start_of_day = today.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = today.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Convert to UTC for API
        start_str = start_of_day.astimezone(pytz.UTC).isoformat().replace('+00:00', 'Z')
        end_str = end_of_day.astimezone(pytz.UTC).isoformat().replace('+00:00', 'Z')
        
        response = client.account_orders_all(
            fromEnteredTime=start_str,
            toEnteredTime=end_str,
            status="FILLED"
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to get orders: {response.status_code} - {response.text}")
            return None
            
        orders = response.json()
        
        # Process orders
        trades = []
        for order in orders:
            trade_infos = extract_trade_info(order)
            trades.extend(trade_infos)
        
        if not trades:
            logger.info("No trades found for today")
            return None
            
        # Create DataFrame
        df = pd.DataFrame(trades)
        
        # Calculate P&L for each symbol
        results = []
        for symbol in df['Symbol'].unique():
            symbol_trades = df[df['Symbol'] == symbol].copy()
            
            # Separate shorts and covers
            covers = symbol_trades[symbol_trades['Side'].isin(['BUY', 'BUY_TO_COVER'])]
            shorts = symbol_trades[symbol_trades['Side'].isin(['SELL', 'SELL_SHORT'])]
            
            if not covers.empty and not shorts.empty:
                cover_value = covers['Total Value'].sum()
                short_value = shorts['Total Value'].sum()
                cover_quantity = covers['Quantity'].sum()
                short_quantity = shorts['Quantity'].sum()
                
                results.append({
                    'Date': today.strftime('%Y-%m-%d'),
                    'Symbol': symbol,
                    'Total $ Shorted': short_value,
                    'Total $ Covered': cover_value,
                    'Avg Short Price': short_value / short_quantity if short_quantity > 0 else 0,
                    'Avg Cover Price': cover_value / cover_quantity if cover_quantity > 0 else 0,
                    'P&L': short_value - cover_value
                })
        
        # Create results DataFrame
        results_df = pd.DataFrame(results)
        
        # Handle existing file and calculate grand totals
        results_dir = Path('logs/performance')
        results_dir.mkdir(parents=True, exist_ok=True)
        summary_file = results_dir / 'performance_summary.csv'
        
        # Combine with existing data if file exists
        if summary_file.exists():
            existing_df = pd.read_csv(summary_file)
            # Remove the totals row if it exists
            existing_df = existing_df[existing_df['Date'] != 'TOTALS']
            # Remove today's entries if they exist
            existing_df = existing_df[existing_df['Date'] != today.strftime('%Y-%m-%d')]
            
            # Convert currency strings back to numbers for calculations
            for col in ['Total $ Shorted', 'Total $ Covered', 'P&L']:
                existing_df[col] = existing_df[col].str.replace('$', '').str.replace(',', '').astype(float)
            
            # Combine existing and new data
            all_results = pd.concat([existing_df, results_df], ignore_index=True)
        else:
            all_results = results_df
        
        # Calculate grand totals using all data
        total_short_value = all_results['Total $ Shorted'].sum()
        total_cover_value = all_results['Total $ Covered'].sum()
        total_pnl = total_short_value - total_cover_value
        
        # Calculate overall win rate
        total_trades = len(all_results)
        winning_trades = len(all_results[all_results['P&L'] > 0])
        win_rate = (winning_trades/total_trades*100) if total_trades > 0 else 0
        
        # Calculate total return percentage
        total_return_pct = (total_pnl / total_short_value * 100) if total_short_value > 0 else 0
        
        # Create totals row
        totals_row = pd.DataFrame([{
            'Date': 'TOTALS',
            'Symbol': f'Win Rate: {win_rate:.1f}%',
            'Total $ Shorted': total_short_value,
            'Total $ Covered': total_cover_value,
            'Avg Short Price': None,
            'Avg Cover Price': None,
            'P&L': total_pnl,
            'Return %': f'{total_return_pct:.2f}%'
        }])
        
        # Combine all results with totals row
        final_df = pd.concat([all_results, totals_row], ignore_index=True)
        
        # Format numeric columns as currency strings
        for col in ['Total $ Shorted', 'Total $ Covered', 'P&L']:
            final_df[col] = final_df[col].apply(lambda x: f"${x:,.2f}" if pd.notnull(x) else x)
        
        # Format average prices
        for col in ['Avg Short Price', 'Avg Cover Price']:
            final_df[col] = final_df[col].apply(lambda x: f"{x:.4f}" if pd.notnull(x) else x)
        
        # Save the updated summary
        final_df.to_csv(summary_file, index=False)
        
        # Print summary for today
        total_pnl = results_df['P&L'].sum()
        winning_trades = len(results_df[results_df['P&L'] > 0])
        total_trades = len(results_df)
        
        logger.info(f"\nTrade Summary for {today.strftime('%Y-%m-%d')}:")
        logger.info(f"Total P&L: ${total_pnl:.2f}")
        logger.info(f"Number of Symbols Traded: {total_trades}")
        logger.info(f"Winning Trades: {winning_trades}")
        if total_trades > 0:
            logger.info(f"Win Rate: {(winning_trades/total_trades)*100:.1f}%")
        
        return results_df
        
    except Exception as e:
        logger.error(f"Error analyzing trades: {str(e)}")
        return None


