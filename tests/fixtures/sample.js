// Greets a user by name.
function greet(name) {
    return `Hello, ${name}!`;
}

// Arrow function assigned to const — NOT extracted (not a declaration).
const helper = (x) => x * 2;

// A simple user class.
class User {
    constructor(name) {
        this.name = name;
    }

    // Returns the display name in uppercase.
    getDisplayName() {
        return this.name.toUpperCase();
    }
}

// A repository for managing users.
class UserRepository {
    findById(id) {
        return null;
    }
}
