#!/usr/bin/env python3
"""
PDGA Disc Golf Database Loader

Reads master.csv (PDGA approved discs) and populates an SQLite database.
Includes additional columns for flight path data (bh1-3, fh1-3).
"""

import sqlite3
import csv
import os
from pathlib import Path


def create_database(db_path: str) -> sqlite3.Connection:
    """Create SQLite database and discs table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS discs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manufacturer TEXT,
            disc_model TEXT,
            max_weight REAL,
            diameter REAL,
            height REAL,
            rim_depth REAL,
            inside_rim_diameter REAL,
            rim_thickness REAL,
            rim_depth_diameter_ratio REAL,
            rim_configuration REAL,
            flexibility REAL,
            class TEXT,
            max_weight_vint REAL,
            last_year_production INTEGER,
            certification_number TEXT,
            approved_date TEXT,
            bh1 TEXT,
            bh2 TEXT,
            bh3 TEXT,
            fh1 TEXT,
            fh2 TEXT,
            fh3 TEXT,
            UNIQUE(manufacturer, disc_model)
        )
    ''')
    
    conn.commit()
    return conn


def parse_float(value: str) -> float | None:
    """Parse string to float, returning None for empty/invalid values."""
    if not value or value.strip() == '':
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def parse_int(value: str) -> int | None:
    """Parse string to int, returning None for empty/invalid values."""
    if not value or value.strip() == '':
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def load_csv_to_db(csv_path: str, conn: sqlite3.Connection) -> int:
    """Load CSV data into database. Returns number of rows inserted."""
    cursor = conn.cursor()
    rows_inserted = 0
    rows_skipped = 0
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO discs (
                        manufacturer,
                        disc_model,
                        max_weight,
                        diameter,
                        height,
                        rim_depth,
                        inside_rim_diameter,
                        rim_thickness,
                        rim_depth_diameter_ratio,
                        rim_configuration,
                        flexibility,
                        class,
                        max_weight_vint,
                        last_year_production,
                        certification_number,
                        approved_date,
                        bh1, bh2, bh3,
                        fh1, fh2, fh3
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row.get('Manufacturer / Distributor', '').strip(),
                    row.get('Disc Model', '').strip(),
                    parse_float(row.get('Max Weight (gr)', '')),
                    parse_float(row.get('Diameter (cm)', '')),
                    parse_float(row.get('Height (cm)', '')),
                    parse_float(row.get('Rim Depth (cm)', '')),
                    parse_float(row.get('Inside Rim Diameter (cm)', '')),
                    parse_float(row.get('Rim Thickness (cm)', '')),
                    parse_float(row.get('Rim Depth / Diameter Ratio (%)', '')),
                    parse_float(row.get('Rim Configuration', '')),
                    parse_float(row.get('Flexibility (kg)', '')),
                    row.get('Class', '').strip() or None,
                    parse_float(row.get('Max Weight Vint (gr)', '')),
                    parse_int(row.get('Last Year Production', '')),
                    row.get('Certification Number', '').strip() or None,
                    row.get('Approved Date', '').strip() or None,
                    None, None, None,  # bh1, bh2, bh3
                    None, None, None   # fh1, fh2, fh3
                ))
                
                if cursor.rowcount > 0:
                    rows_inserted += 1
                else:
                    rows_skipped += 1
                    
            except Exception as e:
                print(f"Error inserting row: {row.get('Disc Model', 'Unknown')} - {e}")
                rows_skipped += 1
    
    conn.commit()
    return rows_inserted, rows_skipped


def main():
    # Paths
    script_dir = Path(__file__).parent
    csv_path = script_dir / 'master.csv'
    db_path = script_dir / 'discs.db'
    
    # Check CSV exists
    if not csv_path.exists():
        print(f"Error: {csv_path} not found")
        print("Please ensure master.csv is in the same directory as this script.")
        return 1
    
    # Remove existing database to start fresh (optional - comment out to append)
    if db_path.exists():
        os.remove(db_path)
        print(f"Removed existing database: {db_path}")
    
    # Create database and load data
    print(f"Creating database: {db_path}")
    conn = create_database(str(db_path))
    
    print(f"Loading data from: {csv_path}")
    inserted, skipped = load_csv_to_db(str(csv_path), conn)
    
    # Summary
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM discs")
    total = cursor.fetchone()[0]
    
    print(f"\n=== Summary ===")
    print(f"Rows inserted: {inserted}")
    print(f"Rows skipped (duplicates): {skipped}")
    print(f"Total records in database: {total}")
    
    # Show sample data
    print(f"\n=== Sample Records ===")
    cursor.execute("SELECT manufacturer, disc_model, max_weight, diameter FROM discs LIMIT 5")
    for row in cursor.fetchall():
        print(f"  {row[0]} - {row[1]} ({row[2]}g, {row[3]}cm)")
    
    # Show table schema
    print(f"\n=== Table Schema ===")
    cursor.execute("PRAGMA table_info(discs)")
    for col in cursor.fetchall():
        print(f"  {col[1]}: {col[2]}")
    
    conn.close()
    print(f"\nDatabase created successfully: {db_path}")
    return 0


if __name__ == '__main__':
    exit(main())