-------------------- MODULE AssignmentGeneration --------------------
EXTENDS Naturals, FiniteSets, Sequences

CONSTANTS Workers, NoWorker, MaxGeneration, MaxSteps, EnforceGeneration, InjectRejectedWrite

ASSUME Workers # {}
ASSUME NoWorker \notin Workers
ASSUME MaxGeneration \in Nat \ {0}
ASSUME MaxSteps \in Nat \ {0}
ASSUME EnforceGeneration \in BOOLEAN
ASSUME InjectRejectedWrite \in BOOLEAN

VARIABLES generation, assigned, owner, issued, writes, attempts, steps

vars == <<generation, assigned, owner, issued, writes, attempts, steps>>

WriteRecord(token) ==
    [token |-> token, current |-> generation]

AcceptedAttempt == [accepted |-> TRUE]

RejectedAttempt == [accepted |-> FALSE]

Init ==
    /\ generation = 0
    /\ assigned = FALSE
    /\ owner = NoWorker
    /\ issued = <<>>
    /\ writes = <<>>
    /\ attempts = <<>>
    /\ steps = 0

Assign(worker) ==
    /\ worker \in Workers
    /\ generation < MaxGeneration
    /\ generation' = generation + 1
    /\ assigned' = TRUE
    /\ owner' = worker
    /\ issued' = Append(issued, [token |-> generation + 1, worker |-> worker])
    /\ writes' = writes
    /\ attempts' = attempts
    /\ steps' = steps + 1

Revoke ==
    /\ assigned
    /\ generation < MaxGeneration
    /\ generation' = generation + 1
    /\ assigned' = FALSE
    /\ owner' = NoWorker
    /\ issued' = issued
    /\ writes' = writes
    /\ attempts' = attempts
    /\ steps' = steps + 1

WriteAllowed(token, worker) ==
    /\ \E i \in 1..Len(issued):
          /\ issued[i].token = token
          /\ issued[i].worker = worker
    /\ assigned
    /\ (token = generation \/ ~EnforceGeneration)

AcceptedWrite(token, worker) ==
    /\ token \in 0..MaxGeneration
    /\ worker \in Workers
    /\ WriteAllowed(token, worker)
    /\ writes' = Append(writes, WriteRecord(token))
    /\ attempts' = Append(attempts, AcceptedAttempt)
    /\ UNCHANGED <<generation, assigned, owner, issued>>
    /\ steps' = steps + 1

RejectedWrite(token, worker) ==
    /\ token \in 0..MaxGeneration
    /\ worker \in Workers
    /\ ~WriteAllowed(token, worker)
    /\ writes' =
          IF InjectRejectedWrite /\ assigned
          THEN Append(writes, WriteRecord(generation))
          ELSE writes
    /\ attempts' = Append(attempts, RejectedAttempt)
    /\ UNCHANGED <<generation, assigned, owner, issued>>
    /\ steps' = steps + 1

AttemptWrite(token, worker) ==
    AcceptedWrite(token, worker) \/ RejectedWrite(token, worker)

Next ==
    /\ steps < MaxSteps
    /\ \/ \E worker \in Workers : Assign(worker)
       \/ Revoke
       \/ \E token \in 0..MaxGeneration, worker \in Workers :
              AttemptWrite(token, worker)

Spec == Init /\ [][Next]_vars

TypeOK ==
    /\ generation \in 0..MaxGeneration
    /\ assigned \in BOOLEAN
    /\ owner \in Workers \cup {NoWorker}
    /\ assigned = (owner \in Workers)
    /\ issued \in Seq([token : 1..MaxGeneration, worker : Workers])
    /\ Len(issued) <= MaxGeneration
    /\ writes \in Seq([token : 0..MaxGeneration, current : 0..MaxGeneration])
    /\ attempts \in Seq([accepted : BOOLEAN])
    /\ Len(writes) <= MaxSteps
    /\ Len(attempts) <= MaxSteps
    /\ steps \in 0..MaxSteps

NoStaleWrites ==
    \A i \in 1..Len(writes):
        writes[i].token = writes[i].current

ActiveAssignmentHasIssuedToken ==
    assigned =>
        \E i \in 1..Len(issued):
            /\ issued[i].token = generation
            /\ issued[i].worker = owner

WritesMatchAcceptedAttempts ==
    Len(writes) = Cardinality(
        {i \in 1..Len(attempts): attempts[i].accepted}
    )

=============================================================================
