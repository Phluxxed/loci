# Loci

Loci records source evidence and the repository relationships justified by it.

## Language

**Type use**: An authored type expression's dependency on a named declaration,
including a value declaration named by a type query. It does not imply execution
or a computed, fully inferred type.
_Avoid_: type inference, runtime reference

**Declaration owner**: The declaration whose authored contract contains a type
use or heritage clause. Ownership does not transfer to an enclosing declaration
merely because the actual owner cannot be identified.
_Avoid_: executable owner, enclosing file

**Authored heritage**: An explicit declaration that one class or interface
extends another named declaration, or that a class implements one. It does not
enumerate structural compatibility, validate a program, or identify dispatch.
_Avoid_: complete implementation set, inferred inheritance

**Authored embedding**: A Go struct field or interface element explicitly names
an embedded type. It identifies that declared dependency without establishing
class inheritance, an inferred method set, interface satisfaction or the target
of a promoted-member call.
_Avoid_: inheritance, inferred implementation, promoted dispatch

**Authored trait contract**: A Rust declaration explicitly requires a trait,
including a trait that names a supertrait. The requirement does not identify a
trait-object call target, a monomorphized runtime target or every implementing
type.
_Avoid_: dynamic dispatch, implementation census

**Implementation site**: A separate Rust declaration that names a self type
and, for a trait implementation, the implemented trait. Its methods belong to
that site; the declaration does not transfer ownership to the trait or self
type.
_Avoid_: inferred implementation, runtime target

**Candidate universe**: The stated set of possible targets considered under a
particular binding scope. Completeness within that universe does not establish
completeness across the repository or language.
_Avoid_: all possible targets, proven reachability

**Retrieval intent**: The caller's stated purpose for selecting repository
evidence, such as locating code, understanding type dependencies or exploring
known dependents. It changes selection without changing relationship meaning.
_Avoid_: inferred task, answerability decision

**Selection relevance**: A reason to include evidence for the current request.
A proven dependency can have low selection relevance, and a strong name match
does not prove a dependency.
_Avoid_: relationship certainty, required context
