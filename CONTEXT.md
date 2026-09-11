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

**Candidate universe**: The stated set of possible targets considered under a
particular binding scope. Completeness within that universe does not establish
completeness across the repository or language.
_Avoid_: all possible targets, proven reachability
