"""Demo: basic pysqlite usage examples."""

from pysqlite import Database


def main():
    db = Database(':memory:')

    db.execute("CREATE TABLE users (id INT PRIMARY KEY, name TEXT, age INT)")
    db.execute("INSERT INTO users VALUES (1, 'Alice', 30)")
    db.execute("INSERT INTO users VALUES (2, 'Bob', 25)")
    db.execute("INSERT INTO users VALUES (3, 'Charlie', 35)")

    res = db.execute("SELECT * FROM users ORDER BY name")
    print("All users:")
    for row in res:
        print(f"  {row}")

    res = db.execute("SELECT name, age FROM users WHERE age > 28")
    print("\nUsers over 28:")
    for row in res:
        print(f"  {row}")

    res = db.execute("SELECT COUNT(*), AVG(age) FROM users")
    print(f"\nCount: {res[0][0]}, Avg age: {res[0][1]}")

    db.execute("UPDATE users SET age = 31 WHERE id = 1")
    res = db.execute("SELECT name, age FROM users WHERE id = 1")
    print(f"\nAfter update: {res[0]}")

    db.execute("DELETE FROM users WHERE name = 'Charlie'")
    res = db.execute("SELECT COUNT(*) FROM users")
    print(f"\nAfter delete: {res[0][0]} users remaining")

    db.close()
    print("\nDone!")


if __name__ == '__main__':
    main()
