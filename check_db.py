import sqlite3

DATABASE_FILE = 'weather_forecasts.db'

def check_database_content():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM short_term_forecasts LIMIT 5;")
        rows = cursor.fetchall()
        
        if rows:
            print("--- Database Content (First 5 Rows) ---")
            # Print column names
            col_names = [description[0] for description in cursor.description]
            print(col_names)
            for row in rows:
                print(row)
            print("----------------------------------------")
        else:
            print("No data found in short_term_forecasts table.")
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_database_content() 