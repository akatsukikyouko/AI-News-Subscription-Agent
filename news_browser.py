from DrissionPage import Chromium,ChromiumOptions
import time
import json
from fastmcp import FastMCP, Context



co = ChromiumOptions()
#无头模式
#co = ChromiumOptions().headless()
#我用的是edge，如果想用别的浏览器，请改变这里的路径
#co.set_browser_path('C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe')

# 启动或接管浏览器，并获取标签页对象
tab = Chromium(addr_or_opts=co).latest_tab

# 初始化FastMCP服务器
mcp = FastMCP(name="dariy_news")


@mcp.tool(
    name="get_news_links",
    description="""从新闻网站中，获取所有新闻的链接。

    该工具需要一个URLs列表作为输入。每个URL都应包含在一个字典中，字典的键为'url'。

    输入示例:
    [
        {"url": "https://36kr.com/information/AI/"},
        {"url": "https://news.yiche.com/"}
    ]
    """,
)
async def get_news_links(urls: list = None): 
    
    if urls is None:
        return json.dumps({"error": "No news URLs provided."}, ensure_ascii=False, indent=2)
    print(f"获取新闻链接：{urls}")
    # 构建链接数据列表
    links_data = []
    for url_dict in urls:
        try:    
            url = url_dict.get('url') 
            if url: 
                tab.get(url)
                titles = tab.eles('tag:a')
                for title in titles:
                    #减少token占用，将标题设置为8个字符以上
                    if(len(title.text) > 8):
                        links_data.append({
                            "title": title.text,
                            "url": title.link
                        })
            else:
                print(f"警告：字典中未找到'url'键：{url_dict}")
        except Exception as e:
            print(f"错误：获取新闻链接时发生错误：{e}")
    
    # 将列表转换为JSON格式
    return json.dumps(links_data, ensure_ascii=False, indent=2)

# 获取新闻内容的mcp服务
@mcp.tool(
    name="get_news_content",
    description="获取输入新闻链接的新闻内容",
)
async def get_news_content(url: str):
    tab.get(url)
    news_text=''
    contents = tab.eles('tag:p')
    for content in contents:
        news_text += content.text
    return news_text


if __name__ == "__main__":
    # 启动 FastMCP 主服务
    mcp.run(transport="streamable-http", host="0.0.0.0", port=9017)