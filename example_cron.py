import barkueue as bark

app = bark.app([])
scheduler = bark.Scheduler(app)  # 自动注册 datasource 到 app.sources

@app.handler("report.gen")
def gen_report(app: bark.Application, task: bark.Task) -> None:
    print(f"生成报告: {task.message}")

scheduler.add("* * * * * */5", bark.Task("report.gen", "weekly_report 1"))
scheduler.add("* * * * * */5", bark.Task("report.gen", "weekly_report 2"))
app.run()
