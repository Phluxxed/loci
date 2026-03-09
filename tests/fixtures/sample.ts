/** A simple greeter function. */
function greet(name: string): string {
    return `Hello, ${name}`;
}

/** A user class. */
class User {
    name: string;

    /** Create a new user. */
    constructor(name: string) {
        this.name = name;
    }

    /** Get the display name. */
    getDisplayName(): string {
        return this.name.toUpperCase();
    }
}

type UserId = string;
