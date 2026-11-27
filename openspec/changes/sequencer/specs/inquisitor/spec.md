## MODIFIED Requirements

### Requirement: A numbered Inquisitor reply is about the item at that number

An `Inquisitor: ` reply holding `question <n>: ` after its prefix SHALL be
about item `<n>`, counted from 1, among the open-questions items of the post,
or Linear or Discord message, it replies to or names in its `Re: ` line
(the line linking what it answers),
or, one past the last item, about that message's sentences ending in `?`
outside its open-questions section. A numbered reply SHALL be input when the message
it is about was edited after the reply, save as *A sequencer block's update
keeps a numbered reply* allows.

#### Scenario: A numbered reply settles only its item

- **WHEN** an agent's post lists three questions in one open-questions
  section, and a reply starting `Inquisitor: question 2: filter 4` has its
  miss file
- **THEN** the agent acts on it for the second item only, and the first
  and third stand

#### Scenario: A numbered reply to a post edited since is input

- **WHEN** the agent's post was edited after a reply starting `Inquisitor:
  question 2: filter 4` was posted
- **THEN** the reply is input, since the number may point at another item

#### Scenario: A reply one past the last item settles the sentences outside the list

- **WHEN** an agent's post lists two questions in its open-questions
  section and asks another in a sentence ending in `?` outside it, and a
  reply starting `Inquisitor: question 3: filter 4` has its miss file
- **THEN** the agent acts on it for that sentence only, and both items
  stand

## ADDED Requirements

### Requirement: A sequencer block's update keeps a numbered reply

An edit to an issue's or pull request's body after a numbered
`Inquisitor: ` reply SHALL leave the reply in force when the body the
reply saw and the body now differ only in blank lines and in sequencer
blocks added whole or changed between unchanged markers. A sequencer block
runs from a line that is exactly `<!-- sequencer:begin -->` to the next
line that is exactly `<!-- sequencer:end -->`. A removed block, or an edit
history without the body the reply saw, SHALL make the reply input.

#### Scenario: A sequencer block's update keeps a numbered reply

- **WHEN** an agent's issue description lists three questions, a reply
  starting `Inquisitor: question 2: filter 4` has its miss file, and the
  sequencer then rewrote only the text between the description's
  `<!-- sequencer:begin -->` and `<!-- sequencer:end -->` lines
- **THEN** the agent acts on the reply for the second item
- **AND** an edit that also changed a line outside those markers, other
  than a blank line, makes the reply input

#### Scenario: A sequencer block added keeps a numbered reply

- **WHEN** a reply starting `Inquisitor: question 2: filter 4` has its
  miss file, and the sequencer then added a whole block, from its
  `<!-- sequencer:begin -->` line to its `<!-- sequencer:end -->` line, to
  the issue's description, as it does when it starts ordering the issue
- **THEN** the agent acts on the reply for the second item
- **AND** a block removed when the sequencer stops ordering the issue
  makes the reply input

#### Scenario: A reply whose body is gone from the edit history is input

- **WHEN** a reply starting `Inquisitor: question 2: filter 4` has its
  miss file, the sequencer then rewrote the issue's block, and the
  description's revision the reply saw was deleted from its edit history
- **THEN** the reply is input
