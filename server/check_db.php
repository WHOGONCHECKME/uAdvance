<?php
// Set up SQLite database connection
$dsn = 'sqlite:' . __DIR__ . '/contacts.db';
try {
    $db = new PDO($dsn);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    echo "Database connection successful.<br>";
    
    // Check if the table exists
    $result = $db->query("SELECT name FROM sqlite_master WHERE type='table' AND name='contacts'");
    if ($result && $result->fetch()) {
        echo "Table 'contacts' exists.<br>";
    } else {
        echo "Table 'contacts' does not exist.<br>";
    }
} catch (PDOException $e) {
    echo "Connection failed: " . $e->getMessage();
}
?>