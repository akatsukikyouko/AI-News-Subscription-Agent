import sqlite3
from datetime import datetime, timezone, timedelta

DATABASE = 'news_app.db'

def get_db():
    """
    Establishes a connection to the SQLite database.
    Sets row_factory to sqlite3.Row to allow accessing columns by name.
    """
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db()
    cursor = conn.cursor()
    

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL, -- Still keeping prompt for general keywords
            schedule_time TEXT NOT NULL, -- Format HH:MM (e.g., '09:00')
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP DEFAULT NULL -- Used for soft deletion
        )
    ''')

    # News sources table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, -- Name must be unique
            url TEXT NOT NULL UNIQUE,   -- URL must be unique
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Junction table for subscriptions and news sources (many-to-many relationship)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscription_news_sources (
            subscription_id INTEGER NOT NULL,
            news_source_id INTEGER NOT NULL,
            PRIMARY KEY (subscription_id, news_source_id),
            FOREIGN KEY (subscription_id) REFERENCES subscriptions (id) ON DELETE CASCADE,
            FOREIGN KEY (news_source_id) REFERENCES news_sources (id) ON DELETE CASCADE
        )
    ''')

    # Generated reports table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subscription_id INTEGER NOT NULL,
        content TEXT,
        status TEXT NOT NULL, -- e.g., 'queued', 'running', 'completed', 'failed'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (subscription_id) REFERENCES subscriptions (id)
    )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized.")

def add_subscription(name, prompt, schedule_time, news_source_ids):
    """
    Adds a new subscription plan to the database and links it to selected news sources.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO subscriptions (name, prompt, schedule_time) VALUES (?, ?, ?)',
                 (name, prompt, schedule_time))
    subscription_id = cursor.lastrowid

    # Link the new subscription to its selected news sources
    for source_id in news_source_ids:
        cursor.execute('INSERT INTO subscription_news_sources (subscription_id, news_source_id) VALUES (?, ?)',
                       (subscription_id, source_id))
    conn.commit()
    conn.close()

def delete_subscription(sub_id):
    """
    Soft deletes a subscription by setting the 'deleted_at' timestamp to the current time.
    This keeps the record in the database but marks it as inactive.
    """
    conn = get_db()
    # Use datetime.now() to get the current timestamp for soft deletion
    conn.execute('UPDATE subscriptions SET deleted_at = ? WHERE id = ?', 
                (datetime.now(), sub_id))
    conn.commit()
    conn.close()

def add_news_source(name, url):
    """Adds a new news source to the database."""
    conn = get_db()
    conn.execute('INSERT INTO news_sources (name, url) VALUES (?, ?)', (name, url))
    conn.commit()
    conn.close()

def delete_news_source(source_id):
    """
    Deletes a news source from the database.
    Note: ON DELETE CASCADE in subscription_news_sources table will handle
    deleting associated entries in that junction table.
    """
    conn = get_db()
    conn.execute('DELETE FROM news_sources WHERE id = ?', (source_id,))
    conn.commit()
    conn.close()

def get_all_news_sources():
    """Retrieves all news sources from the database, ordered by name."""
    conn = get_db()
    sources = conn.execute('SELECT * FROM news_sources ORDER BY name').fetchall()
    conn.close()
    return sources

def get_news_sources_for_subscription(subscription_id):
    """Retrieves all news sources linked to a specific subscription."""
    conn = get_db()
    sources = conn.execute('''
        SELECT ns.id, ns.name, ns.url
        FROM news_sources ns
        JOIN subscription_news_sources sns ON ns.id = sns.news_source_id
        WHERE sns.subscription_id = ?
    ''', (subscription_id,)).fetchall()
    conn.close()
    return sources

def get_all_subscriptions_with_status():
    """
    Retrieves all active (non-soft-deleted) subscriptions along with their latest report status.
    Handles parsing of timestamps, including fractional seconds.
    """
    conn = get_db()
    rows = conn.execute('''
        SELECT 
            s.id, 
            s.name, 
            s.prompt, 
            s.schedule_time, 
            r.id as report_id,
            r.status, 
            r.created_at,
            s.deleted_at
        FROM subscriptions s
        LEFT JOIN (
            SELECT 
                subscription_id, 
                MAX(created_at) as max_created_at
            FROM reports
            GROUP BY subscription_id
        ) latest_report ON s.id = latest_report.subscription_id
        LEFT JOIN reports r ON s.id = r.subscription_id AND r.created_at = latest_report.max_created_at
        WHERE s.deleted_at IS NULL -- Crucial: Only retrieve subscriptions that are NOT soft-deleted
        ORDER BY s.created_at DESC
    ''').fetchall()
    conn.close()
    
    subscriptions = []
    for row in rows:
        sub = dict(row) # Convert sqlite3.Row to a mutable dictionary
        
        # Parse 'created_at' timestamp, handling potential fractional seconds
        if sub['created_at']:
            # Split the string at '.' and take the first part to remove fractional seconds
            sub['created_at'] = datetime.strptime(sub['created_at'].split('.')[0], '%Y-%m-%d %H:%M:%S')
            # Convert to UTC and then to a specific timezone (e.g., UTC+8 for CST)
            sub['created_at'] = sub['created_at'].replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
        
        # Parse 'deleted_at' timestamp, handling potential fractional seconds
        if sub['deleted_at']:
            sub['deleted_at'] = datetime.strptime(str(sub['deleted_at']).split('.')[0], '%Y-%m-%d %H:%M:%S')
            sub['deleted_at'] = sub['deleted_at'].replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
        
        # Fetch news sources for each subscription
        sub['news_sources'] = get_news_sources_for_subscription(sub['id'])
        subscriptions.append(sub)
        
    return subscriptions

def get_subscription_by_id(sub_id):
    """Retrieves a single subscription by its ID."""
    conn = get_db()
    sub = conn.execute('SELECT * FROM subscriptions WHERE id = ?', (sub_id,)).fetchone()
    conn.close()
    if sub:
        sub = dict(sub)
        # Also fetch associated news sources for this single subscription
        sub['news_sources'] = get_news_sources_for_subscription(sub_id)
        # Parse deleted_at if it exists, handling fractional seconds
        if sub['deleted_at']:
            sub['deleted_at'] = datetime.strptime(str(sub['deleted_at']).split('.')[0], '%Y-%m-%d %H:%M:%S')
            sub['deleted_at'] = sub['deleted_at'].replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
    return sub

def create_report_entry(subscription_id):
    """Creates a new report entry in the database with 'queued' status."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO reports (subscription_id, status) VALUES (?, ?)', 
                   (subscription_id, 'queued'))
    report_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return report_id

def update_report(report_id, status, content=None):
    """Updates the status and optionally content of an existing report."""
    conn = get_db()
    if content:
        conn.execute('UPDATE reports SET status = ?, content = ? WHERE id = ?', 
                     (status, content, report_id))
    else:
        conn.execute('UPDATE reports SET status = ? WHERE id = ?', (status, report_id))
    conn.commit()
    conn.close()


def get_report_by_id(report_id):
    """Retrieves a single report by its ID, joining with subscription name."""
    conn = get_db()
    row = conn.execute('SELECT r.*, s.name FROM reports r JOIN subscriptions s ON r.subscription_id = s.id WHERE r.id = ?', 
                          (report_id,)).fetchone()
    conn.close()
    
    if not row:
        return None

    report = dict(row) # Convert sqlite3.Row to a mutable dictionary
    if report['created_at']:
        # Parse 'created_at' timestamp, handling potential fractional seconds
        report['created_at'] = datetime.strptime(report['created_at'].split('.')[0], '%Y-%m-%d %H:%M:%S')
        report['created_at'] = report['created_at'].replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8)))
        
    return report

if __name__ == '__main__':
    # If this file is run directly, it will initialize the database.
    init_db()
