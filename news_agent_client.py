# 导入 pydantic-ai 相关模块，这些模块在 mcprun 函数中使用
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.profiles._json_schema import InlineDefsJsonSchemaTransformer
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider
import asyncio
import json


from datetime import datetime

with open('config.json', 'r') as config_file:
    config = json.load(config_file)

async def mcprun(question: str, news_urls: list = None) -> str: # Added news_urls parameter
    """
    使用 Pydantic-AI Agent 运行 MCP 服务器并处理问题。
    每次调用 agent 都会重新创建上下文，不保留历史（确保不传入旧的 message_history）

    Args:
        question (str): 需要 Agent 处理的问题。
        news_urls (list): A list of URLs to fetch news from.

    Returns:
        str: Agent 的处理结果。
    """


    model = OpenAIModel(
        config.get("llm_model_name"),
        provider=OpenAIProvider(
            base_url=config.get("base_url"),
            api_key=config.get("api_key"),
        ),
        profile=OpenAIModelProfile(
            json_schema_transformer=InlineDefsJsonSchemaTransformer,
            openai_supports_strict_tool_definition=False
        )
    )
    nowtime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


    systemprompt = f'''
    你是一个新闻整理助手，可以精准调用mcp工具，获取并整理用户所关心的新闻内容。现在的时间是{nowtime}
    首先，你需要调用工具获取所有的新闻链接。
    用户会输出一些关键词，这些代表了用户所关心的内容。
    你需要整理出【头条新闻】（你认为最重要、所有人都特别关心的新闻、链接和500字简介）和【特别关注】（用户输入的关键词相关的新闻、链接和简介），今日总结（给所有你今天读过的新闻做一个1000字左右的总评）三个项目。
    根据整理需求，查询相关新闻详情，最后进行整理。总共列出5条左右不重复的新闻，按重要程度排序。尽可能每个输入的主域名都有新闻。
    你的输出格式如下，请严格按照输出格式来输出：

    ==========================

    您好，今天是x月x日。以下是今天的每日AI报：
    ## 头条新闻
    ### 新闻标题

    新闻简介
    xxxxxxxxxxxxxxxxxxx
    新闻链接
    xxxxxxxxxxxxxxxxxxx

    ---

    ### 新闻标题

    新闻简介
    xxxxxxxxxxxxxxxxxxx
    新闻链接
    xxxxxxxxxxxxxxxxxxx

    ---

    ……
    
    ## 特别关注
    ### 新闻标题
    
    新闻简介
    xxxxxxxxxxxxxxxxxxx
    新闻链接
    xxxxxxxxxxxxxxxxxxx

    ---

    ……
    ## 今日总结
    今日总结内容(三段左右1000字左右的话，使用总分总议论文的格式，体现出你对新闻的理解，不要用markdown等标准格式，而是写成文章形式)

    ==========================
    '''


    initial_message = f"{question}"
    if news_urls:
        initial_message += f"\n请从以下新闻源获取新闻：{news_urls}"

    server = MCPServerStreamableHTTP('http://127.0.0.1:9017/mcp')
    agent = Agent(model,system_prompt=systemprompt, mcp_servers=[server])

    nodes = []
    try:
        async with agent.run_mcp_servers(): # 启动 MCP 服务
            async with agent.iter(initial_message) as agent_run: # Pass initial_message
                async for node in agent_run:
                    print(f"Agent Node: {node}")
                    nodes.append(node)
                    #print(f"所有 Agent Nodes: {nodes}")
            if hasattr(agent_run, 'result') and hasattr(agent_run.result, 'output'):
                return agent_run.result.output
            else:
                print("Agent 运行结果或输出为空。")
                return "未能获取 Agent 的响应。"
    except Exception as e:
        print(f"运行 MCP Agent 时发生错误: {e}")
        return f"运行 Agent 过程中发生错误: {str(e)}"