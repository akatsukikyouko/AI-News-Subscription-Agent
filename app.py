import asyncio
import queue
import threading
from datetime import datetime, timezone, timedelta

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_apscheduler import APScheduler

import database as db

# Assuming news_agent_client.py exists and contains mcprun function
# If not, you might need to mock this or provide the actual implementation.
from news_agent_client import mcprun 

import sqlite3

# --- Configuration ---
task_queue = queue.Queue() # The queue for agent tasks

app = Flask(__name__)
app.config['SECRET_KEY'] = 'agent_news' # Change for production, use a strong, random key

# --- Scheduler Setup ---
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# --- Background Worker ---
def agent_worker():
    """
    Processes tasks from the queue one by one.
    This runs in a separate thread to avoid blocking the Flask main thread.
    """
    print("Agent worker thread started.")
    while True:
        # Get task from the queue: report_id, prompt, news_urls
        report_id, prompt, news_urls = task_queue.get() 
        print(f"Worker picked up task for report ID: {report_id}")
        try:
            # Update status to 'running' in the database
            db.update_report(report_id, 'running')
            
            # Run the asynchronous agent function (mcprun)
            # asyncio.run is used here because mcprun is an async function
            response = asyncio.run(mcprun(prompt, news_urls)) 
            
            # Update status to 'completed' with the generated content
            db.update_report(report_id, 'completed', response)
            print(f"Task for report ID: {report_id} completed successfully.")
            
        except Exception as e:
            # If an error occurs, update the report status to 'failed'
            error_message = f"Agent execution failed for report ID {report_id}: {str(e)}"
            print(error_message)
            db.update_report(report_id, 'failed', error_message)
        finally:
            # Mark the task as done in the queue
            task_queue.task_done()

# Start the worker in a separate thread, making it a daemon thread
# so it exits when the main program exits.
worker_thread = threading.Thread(target=agent_worker, daemon=True)
worker_thread.start()


# --- Scheduled Job ---
@scheduler.task('cron', id='daily_news_job', minute='*') # This job runs every minute
def schedule_daily_tasks():
    """
    Checks every minute if any subscription's scheduled time has arrived.
    Only schedules tasks for active (non-deleted) subscriptions.
    """
    with app.app_context(): # APScheduler jobs run outside the request context, so we need this.
        now_time = datetime.now().strftime('%H:%M')
        print(f"Scheduler checking for tasks at {now_time}...")
        
        # Get all active subscriptions (the database function now filters out deleted ones)
        subscriptions = db.get_all_subscriptions_with_status()
        
        for sub in subscriptions:
            # Check if the current time matches the subscription's schedule time
            # The 'deleted_at' check is implicitly handled by get_all_subscriptions_with_status
            if sub['schedule_time'] == now_time:
                print(f"Scheduling task for subscription: {sub['name']}")
                
                # Get news URLs associated with this subscription
                news_urls = [source['url'] for source in sub['news_sources']]
                
                # Create a new report entry in the database with 'queued' status
                report_id = db.create_report_entry(sub['id'])
                
                # Add the task to the queue for the worker thread to process
                task_queue.put((report_id, sub['prompt'], news_urls))


# --- Flask Routes ---
@app.route('/')
def index():
    """
    Main dashboard showing all active subscriptions and their latest status,
    along with available news sources for modal forms.
    """
    subscriptions = db.get_all_subscriptions_with_status()
    news_sources = db.get_all_news_sources() 
    return render_template('index.html', subscriptions=subscriptions, news_sources=news_sources)

@app.route('/add_subscription', methods=['POST'])
def add_subscription():
    """Handles the form submission for creating a new subscription."""
    name = request.form['name']
    prompt = request.form['prompt']
    schedule_time = request.form['schedule_time']
    selected_news_source_ids = request.form.getlist('news_sources') # Get list of selected source IDs

    if not name or not prompt or not schedule_time or not selected_news_source_ids:
        flash('所有字段和至少一个新闻源都是必填项！', 'error')
    else:
        # Convert selected IDs to integers
        selected_news_source_ids = [int(sid) for sid in selected_news_source_ids]
        db.add_subscription(name, prompt, schedule_time, selected_news_source_ids)
        flash(f'订阅计划 "{name}" 添加成功！', 'success')
        
    return redirect(url_for('index'))

@app.route('/run_manual/<int:subscription_id>')
def run_manual(subscription_id):
    """Manually triggers a subscription to run immediately."""
    sub = db.get_subscription_by_id(subscription_id)
    if sub and sub['deleted_at'] is None: 

        news_urls = [source['url'] for source in sub['news_sources']]

        report_id = db.create_report_entry(sub['id'])

        task_queue.put((report_id, sub['prompt'], news_urls))
        flash(f'"{sub["name"]}" 已加入队列。', 'info')
    else:
        flash('订阅计划未找到或已被删除。', 'error')
        
    return redirect(url_for('index'))

@app.route('/delete_subscription/<int:subscription_id>')
def delete_subscription(subscription_id):
    """Soft deletes a subscription plan by setting its deleted_at timestamp."""
    db.delete_subscription(subscription_id)
    flash('订阅计划已删除', 'success')
    return redirect(url_for('index'))

@app.route('/report/<int:report_id>')
def view_report(report_id):
    """Displays the content of a specific report."""
    report = db.get_report_by_id(report_id)
    if report:
        return render_template('report.html', report=report)
    else:
        flash('报告未找到。', 'error')
        return redirect(url_for('index'))

@app.route('/add_news_source', methods=['POST'])
def add_news_source_route():
    """Handles adding a new news source."""
    name = request.form['source_name']
    url = request.form['source_url']
    if not name or not url:
        flash('新闻源名称和URL是必填项！', 'error')
    else:
        try:
            db.add_news_source(name, url)
            flash(f'新闻源 "{name}" 添加成功！', 'success')
        except sqlite3.IntegrityError:
            # Handle cases where name or URL already exists (UNIQUE constraint)
            flash(f'新闻源 "{name}" 或URL "{url}" 已存在。', 'error')
    return redirect(url_for('index'))

@app.route('/delete_news_source/<int:source_id>')
def delete_news_source_route(source_id):
    """Handles deleting a news source."""
    db.delete_news_source(source_id)
    flash('新闻源删除成功！', 'success')
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        db.init_db() # Ensure database is ready before running the app
    # use_reloader=False is important for APScheduler to prevent jobs from running twice
    app.run('0.0.0.0',debug=True, use_reloader=False, port=9039) 
