from google import genai
from google.genai import types
from config import Config
import pandas as pd
import yfinance as yf

def gemini_finance_response(prompt):
    # Define the function declarations for the model

    # function declaration for getting financial data and statements
    get_financial_info_function = {
        "name": "get_financial_info",
        "description": "Retrieve the financial data such as income statements, balance sheets and cashflow using the ticker symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol of a publicly traded company (e.g., 'NVDA' for NVIDIA, 'AAPL' for Apple Inc., 'MSFT' for Microsoft). Must be a valid ticker symbol listed on major stock exchanges.",
                },
            },
            "required": ["ticker"],
        },
    }

    # function declaration for getting stock price (current price and historical price)
    get_stock_price_function = {
        "name": "get_stock_price",
        "description": "Retrieve the current and historical stock price of a publicly traded company using a company's ticker symbol.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol of a publicly traded company (e.g., 'NVDA' for NVIDIA, 'AAPL' for Apple Inc., 'MSFT' for Microsoft). Must be a valid ticker symbol listed on major stock exchanges.",
                },
                "period": {
                    "type": "string",
                    "description": "The period of the stock price to retrieve. Can be '1d', '5d', '2wk', '5wk', '1mo', '3mo', '6mo', 'ytd', '1y', '2y', '5y', '10y', 'max'.",
                },
                "interval": {
                    "type": "string",
                    "description": "The interval of the stock price to retrieve. Can be '1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo'.",
                },
            },
            "required": ["ticker", "period", "interval"],
        },
    }

    # actual function for getting financial data and statements
    def get_financial_info(ticker):
        t = yf.Ticker(ticker)
        
        info = t.info
        company_name = info.get('longName', ticker)
        
        # Get financial statements
        income_stmt = t.financials
        balance_sheet = t.balance_sheet
        cash_flow = t.cashflow

        def format_data(df):
            df.columns = df.columns.strftime('%Y-%m-%d')
            return df.to_json(orient='columns')
        
        return {
            'company_name': company_name,
            'income_statement': format_data(income_stmt),
            'balance_sheet': format_data(balance_sheet),
            'cash_flow': format_data(cash_flow)
        }
    
    # actual function for getting stock price (current price and historical price)
    def get_stock_price(ticker, period, interval):
        t = yf.Ticker(ticker)

        info = t.info
        company_name = info.get('longName', ticker)
        
        # Get stock price
        current_price = info.get('currentPrice', 'None')
        stock_price = t.history(period=period, interval=interval)

        return {
            'company_name': company_name,
            'current_price': current_price,
            'stock_price': stock_price.to_json(orient='columns')
        }

    # Configure the client and tools for function calling
    client = genai.Client(api_key=Config.GEMINI_API_KEY)
    finance_tools = [
        types.Tool(function_declarations=[get_financial_info_function, get_stock_price_function])
    ]
    config = {
        "tools": finance_tools,
        "automatic_function_calling": {"disable": True},
        "tool_config": {"function_calling_config": {"mode": "any"}},
    }

    # Send request with function declarations
    contents = [
        types.Content(
            role="user", parts=[types.Part(text=prompt)]
        )
    ]
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=contents,
        config=config,
    )
    print(response.candidates[0].content.parts[0].function_call)

    # Extract tool call details
    tool_call = response.candidates[0].content.parts[0].function_call

    if tool_call.name == "get_financial_info":
        result = get_financial_info(**tool_call.args)
        print(f"Financial data result: {result}")
    elif tool_call.name == "get_stock_price":
        result = get_stock_price(**tool_call.args)
        print(f"Stock price result: {result}")

    # Create a function response part
    function_response_part = types.Part.from_function_response(
        name=tool_call.name,
        response={"result": result},
    )

    # Append function call and result of the function execution to contents
    contents.append(types.Content(role="model", parts=[types.Part(function_call=tool_call)])) # Append the model's function call message
    contents.append(types.Content(role="user", parts=[function_response_part])) # Append the function response

    final_response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=['You are an AI financial assistant integrated into a Telegram app. Your job is to provide accurate, professional, and insightful responses to users. Your goal is to help users make smarter financial decisions by providing reliable, easy-to-understand insights based on real data and sound financial logic. Maintain a professional and engaging tone in your responses. Do NOT respond to non-financial topics and inform users that you are not able to answer that question.']
        )
    )

    return final_response.text
