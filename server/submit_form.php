<?php
// Set up SQLite database connection
$dsn = 'sqlite:' . __DIR__ . '/contacts.db';
try {
    $db = new PDO($dsn);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    echo "Database connection successful.<br>";
} catch (PDOException $e) {
    echo "Connection failed: " . $e->getMessage();
    exit;
}

// Prepare and execute SQL statement
try {
    if (isset($_POST['name']) && isset($_POST['email']) && isset($_POST['message'])) {
        echo "Form data received: <br>";
        echo "Name: " . htmlspecialchars($_POST['name']) . "<br>";
        echo "Email: " . htmlspecialchars($_POST['email']) . "<br>";
        echo "Message: " . htmlspecialchars($_POST['message']) . "<br>";

        $stmt = $db->prepare("INSERT INTO contacts (name, email, message) VALUES (:name, :email, :message)");
        $stmt->bindParam(':name', $_POST['name']);
        $stmt->bindParam(':email', $_POST['email']);
        $stmt->bindParam(':message', $_POST['message']);
        $stmt->execute();
        echo "Contact saved successfully!";
    } else {
        echo "Required POST parameters are missing.";
    }
} catch (PDOException $e) {
    echo "Error: " . $e->getMessage();
}
?>