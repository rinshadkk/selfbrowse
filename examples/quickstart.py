from selfbrowse import BrowseAgent

result = BrowseAgent("Open news.ycombinator.com and tell me the title of the top story.",
               llm="anthropic:claude-haiku-4-5").run()
print(result.output)
print(result.usage)
