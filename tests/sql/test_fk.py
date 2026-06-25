import pytest
from pysqlite import Database


@pytest.fixture
def db():
    d = Database(':memory:')
    yield d
    d.close()


class TestForeignKey:
    def test_column_level_fk(self, db):
        db.execute('CREATE TABLE parent (id INT PRIMARY KEY)')
        db.execute('CREATE TABLE child (pid INT REFERENCES parent(id))')
        db.execute("INSERT INTO parent VALUES (1)")
        db.execute("INSERT INTO child VALUES (1)")
        res = db.execute('SELECT * FROM child')
        assert res == [[1]]

    def test_table_level_fk(self, db):
        db.execute('CREATE TABLE parent (id INT PRIMARY KEY)')
        db.execute('CREATE TABLE child (pid INT, FOREIGN KEY (pid) REFERENCES parent(id))')
        db.execute("INSERT INTO parent VALUES (1)")
        db.execute("INSERT INTO child VALUES (1)")
        res = db.execute('SELECT * FROM child')
        assert res == [[1]]

    def test_on_update_cascade(self, db):
        db.execute('CREATE TABLE p (id INT PRIMARY KEY)')
        db.execute('CREATE TABLE c (pid INT REFERENCES p(id) ON UPDATE CASCADE)')
        db.execute("INSERT INTO p VALUES (1)")
        db.execute("INSERT INTO p VALUES (2)")
        db.execute("INSERT INTO c VALUES (1)")
        db.execute("INSERT INTO c VALUES (2)")
        db.execute("UPDATE p SET id = 100 WHERE id = 1")
        res = db.execute('SELECT pid FROM c ORDER BY pid')
        assert res == [[2], [100]]

    def test_on_update_set_null(self, db):
        db.execute('CREATE TABLE p (id INT PRIMARY KEY)')
        db.execute('CREATE TABLE c (pid INT REFERENCES p(id) ON UPDATE SET NULL)')
        db.execute("INSERT INTO p VALUES (1)")
        db.execute("INSERT INTO c VALUES (1)")
        db.execute("UPDATE p SET id = 100 WHERE id = 1")
        res = db.execute('SELECT * FROM c')
        assert res == [[None]]

    def test_on_update_set_default(self, db):
        db.execute("CREATE TABLE p (id INT PRIMARY KEY)")
        db.execute("CREATE TABLE c (pid INT DEFAULT 99 REFERENCES p(id) ON UPDATE SET DEFAULT)")
        db.execute("INSERT INTO p VALUES (1)")
        db.execute("INSERT INTO p VALUES (99)")
        db.execute("INSERT INTO c VALUES (1)")
        db.execute("UPDATE p SET id = 100 WHERE id = 1")
        res = db.execute('SELECT * FROM c')
        assert res == [[99]]

    def test_on_delete_cascade(self, db):
        db.execute('CREATE TABLE p (id INT PRIMARY KEY)')
        db.execute('CREATE TABLE c (pid INT REFERENCES p(id) ON DELETE CASCADE)')
        db.execute("INSERT INTO p VALUES (1)")
        db.execute("INSERT INTO p VALUES (2)")
        db.execute("INSERT INTO c VALUES (1)")
        db.execute("INSERT INTO c VALUES (2)")
        db.execute("DELETE FROM p WHERE id = 1")
        res = db.execute('SELECT * FROM c')
        assert res == [[2]]

    def test_on_delete_set_null(self, db):
        db.execute('CREATE TABLE p (id INT PRIMARY KEY)')
        db.execute('CREATE TABLE c (pid INT REFERENCES p(id) ON DELETE SET NULL)')
        db.execute("INSERT INTO p VALUES (1)")
        db.execute("INSERT INTO c VALUES (1)")
        db.execute("DELETE FROM p WHERE id = 1")
        res = db.execute('SELECT * FROM c')
        assert res == [[None]]

    def test_on_delete_set_default(self, db):
        db.execute("CREATE TABLE p (id INT PRIMARY KEY)")
        db.execute("CREATE TABLE c (pid INT DEFAULT 99 REFERENCES p(id) ON DELETE SET DEFAULT)")
        db.execute("INSERT INTO p VALUES (1)")
        db.execute("INSERT INTO p VALUES (99)")
        db.execute("INSERT INTO c VALUES (1)")
        db.execute("DELETE FROM p WHERE id = 1")
        res = db.execute('SELECT * FROM c')
        assert res == [[99]]

    def test_on_delete_restrict(self, db):
        db.execute('CREATE TABLE p (id INT PRIMARY KEY)')
        db.execute('CREATE TABLE c (pid INT REFERENCES p(id) ON DELETE RESTRICT)')
        db.execute("INSERT INTO p VALUES (1)")
        db.execute("INSERT INTO c VALUES (1)")
        with pytest.raises(Exception, match='FOREIGN KEY constraint failed'):
            db.execute("DELETE FROM p WHERE id = 1")

    def test_multiple_fk_columns(self, db):
        db.execute('CREATE TABLE p (a INT, b INT, PRIMARY KEY (a, b))')
        db.execute('CREATE TABLE c (x INT, y INT, FOREIGN KEY (x, y) REFERENCES p(a, b))')
        db.execute("INSERT INTO p VALUES (1, 10)")
        db.execute("INSERT INTO c VALUES (1, 10)")
        res = db.execute('SELECT * FROM c')
        assert res == [[1, 10]]

    def test_fk_with_custom_default(self, db):
        db.execute("CREATE TABLE p (id INT PRIMARY KEY)")
        db.execute("CREATE TABLE c (pid INT DEFAULT 42 REFERENCES p(id) ON UPDATE SET DEFAULT ON DELETE SET DEFAULT)")
        db.execute("INSERT INTO p VALUES (1)")
        db.execute("INSERT INTO p VALUES (42)")
        db.execute("INSERT INTO c VALUES (1)")
        db.execute("UPDATE p SET id = 100 WHERE id = 1")
        res = db.execute('SELECT * FROM c')
        assert res == [[42]]
