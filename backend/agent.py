# backend/agent.py
from typing import TypedDict, Literal
import re
import yfinance as yf
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END

class AssistantState(TypedDict):
    user_message: str
    ticker: str
    stock_data: str
    ai_response: str

llm = ChatOllama(model="gemma3:4b", temperature=0.2)

COMPANY_ALIASES = {
    # India
    "hdfc life": "HDFCLIFE.NS",
    "hdfc bank": "HDFCBANK.NS",
    "hdfc": "HDFCBANK.NS",
    "reliance": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "infosys": "INFY.NS",
    "infy": "INFY.NS",
    "wipro": "WIPRO.NS",
    "itc": "ITC.NS",
    "sbi": "SBIN.NS",
    "icici bank": "ICICIBANK.NS",
    "icici": "ICICIBANK.NS",
    "kotak mahindra bank": "KOTAKBANK.NS",
    "kotak bank": "KOTAKBANK.NS",
    # US
    "apple": "AAPL",
    "microsoft": "MSFT",
    "amazon": "AMZN",
    "amazon.com": "AMZN",
    "firstcry": "FIRSTCRY.NS",
    "brainbees": "BRAINBEES.NS",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "meta": "META",
    "facebook": "META",
    "netflix": "NFLX",
    "amd": "AMD",
    "intel": "INTC",
}

TICKER_PATTERN = re.compile(r"\b[A-Z]{1,5}(?:\.[A-Z]{1,3})?\b")
STOCK_CONTEXT_PATTERN = re.compile(r"\b(stock|share|shares|equity|company|buy|sell|hold|invest|investment)\b", re.IGNORECASE)


def extract_ticker_from_message(message: str) -> str:
    normalized = message.lower()

    # Prefer the longest aliases first so "hdfc bank" wins over "hdfc".
    for alias, ticker in sorted(COMPANY_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return ticker

    # If user typed a symbol directly, use it.
    matches = TICKER_PATTERN.findall(message.upper())
    for match in matches:
        if match not in {"USD", "NSE", "BSE", "BUY", "SELL", "HOLD"}:
            return match

    return ""


def candidate_tickers(ticker: str) -> list[str]:
    if ticker == "FIRSTCRY.NS":
        return ["FIRSTCRY.NS", "BRAINBEES.NS"]
    if ticker == "BRAINBEES.NS":
        return ["BRAINBEES.NS", "FIRSTCRY.NS"]
    return [ticker]


def expand_ticker_candidates(ticker: str) -> list[str]:
    candidates = [ticker]
    if "." not in ticker:
        candidates.extend([f"{ticker}.NS", f"{ticker}.BO"])
    return candidates


def analyze_intent_node(state: AssistantState):
    explicit_ticker = extract_ticker_from_message(state["user_message"])
    if explicit_ticker:
        return {"ticker": explicit_ticker}

    prompt = f"""
    Analyze the user's message: \"{state['user_message']}\"
    If they are asking about a specific company stock, reply ONLY with its exact market ticker symbol.
    If they are not asking about a specific stock, reply with the word 'NONE'.
    Do not include punctuation or extra text.
    """
    response = llm.invoke(prompt)
    ticker_extracted = response.content.strip().upper()
    if ticker_extracted == "NONE":
        ticker_extracted = ""

    # Only accept the model's ticker if it appears to be directly grounded in the user's text.
    if ticker_extracted and ticker_extracted not in state["user_message"].upper():
        ticker_extracted = ""

    return {"ticker": ticker_extracted}


def fetch_stock_node(state: AssistantState):
    market_summary = ""
    for base_ticker in candidate_tickers(state["ticker"]):
        for ticker in expand_ticker_candidates(base_ticker):
            try:
                stock = yf.Ticker(ticker)
                history = stock.history(period="5d", auto_adjust=False)
                last_close = None
                if history is not None and not history.empty:
                    last_close = float(history["Close"].dropna().iloc[-1])

                fast_info = getattr(stock, "fast_info", {}) or {}
                current_price = (
                    fast_info.get("last_price")
                    or fast_info.get("lastPrice")
                    or fast_info.get("regularMarketPrice")
                    or last_close
                )

                info = {}
                try:
                    info = stock.get_info()
                except Exception:
                    info = {}

                pe_ratio = info.get("trailingPE")
                fifty_day_avg = info.get("fiftyDayAverage") or info.get("fiftyDayAveragePrice")

                if current_price is None and pe_ratio is None and fifty_day_avg is None and last_close is None:
                    continue

                market_summary = (
                    f"Ticker: {ticker} | Price: {current_price or 'N/A'} | "
                    f"P/E Ratio: {pe_ratio or 'N/A'} | 50-Day Avg: {fifty_day_avg or 'N/A'}"
                )
                break
            except Exception:
                continue
        if market_summary:
            break
    if not market_summary:
        market_summary = f"Could not fetch real-time data for ticker: {state['ticker']}"
    return {"stock_data": market_summary}


def generate_advice_node(state: AssistantState):
    if state["stock_data"].startswith("Could not fetch real-time data"):
        prompt = (
            f"I couldn't fetch live market data for {state['ticker']}. "
            f"Tell the user the data is unavailable right now and ask them to verify the ticker or try again later. "
            f"User message: {state['user_message']}"
        )
        response = llm.invoke(prompt)
        return {"ai_response": response.content}

    if state["ticker"]:
        prompt = f"""
        You are TradeBuddy AI, a sharp, data-driven financial analyst.
        The user is asking: \"{state['user_message']}\"
        Here is the live real-time market data: {state['stock_data']}

        Provide a highly specific, professional analytical report using these exact headers:

         **MARKET VALUATION BREAKDOWN**
        Evaluate the current price relative to its 50-Day Moving Average. Is it trading at a premium or a discount? State the exact values.

         **RATIO ANALYSIS**
        Analyze the P/E Ratio. Is this company historically overvalued or undervalued compared to its industry standard?

        **ACTIONABLE INSIGHTS & STRATEGY**
        Based on the data metrics above, give a specific recommendation framework (e.g., "Good entry point if it holds above support", "Overextended, watch for a pullback").
        Provide clear support and resistance lookouts.

        *Keep your sentences concise, punchy, and direct.*
        """
    elif STOCK_CONTEXT_PATTERN.search(state["user_message"]):
        prompt = (
            "The user asked about a company or stock, but the ticker is unclear. "
            "Ask a short clarifying question requesting the exact company name or ticker symbol. "
            f"User message: {state['user_message']}"
        )
    else:
        prompt = f"Respond politely to the user as an approachable AI Stock Market Guide: {state['user_message']}"
    response = llm.invoke(prompt)
    return {"ai_response": response.content}


def routing_logic(state: AssistantState) -> Literal["fetch_stock_node", "generate_advice_node"]:
    if state["ticker"]:
        return "fetch_stock_node"
    return "generate_advice_node"

workflow = StateGraph(AssistantState)
workflow.add_node("analyze_intent_node", analyze_intent_node)
workflow.add_node("fetch_stock_node", fetch_stock_node)
workflow.add_node("generate_advice_node", generate_advice_node)

workflow.add_edge(START, "analyze_intent_node")
workflow.add_conditional_edges("analyze_intent_node", routing_logic)
workflow.add_edge("fetch_stock_node", "generate_advice_node")
workflow.add_edge("generate_advice_node", END)

trade_buddy_agent = workflow.compile()
