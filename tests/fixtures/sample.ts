/** A simple greeter function. */
function greet(name: string): string {
    return `Hello, ${name}`;
}

/** An arrow function assigned to a const — NOT extracted (not a declaration). */
const helper = (x: number) => x * 2;

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

/** A type alias. */
type UserId = string;

/** An interface. */
interface UserRepository {
    findById(id: UserId): User | null;
}
