<?php
// Set up SQLite database connection
$dsn = 'sqlite:' . __DIR__ . '/contacts.db';
try {
    $db = new PDO($dsn);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (PDOException $e) {
    echo "Connection failed: " . $e->getMessage();
    exit;
}

// Prepare and execute SQL statement
try {
    $stmt = $db->prepare("INSERT INTO contacts (name, email, message) VALUES (:name, :email, :message)");
    $stmt->bindParam(':name', $_POST['name']);
    $stmt->bindParam(':email', $_POST['email']);
    $stmt->bindParam(':message', $_POST['message']);
    $stmt->execute();
    echo "Contact saved successfully!";
} catch (PDOException $e) {
    echo "Error: " . $e->getMessage();
}
?>