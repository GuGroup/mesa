#let nature-family(body) = {
  set page(paper: "a4", margin: (x: 22mm, y: 24mm))
  set text(font: "New Computer Modern", size: 10pt)
  set par(justify: true, leading: 0.62em)
  body
}

#let nature-title(title, subtitle: none) = {
  align(center)[
    #text(size: 16pt, weight: "bold")[#title]
    #if subtitle != none [
      #linebreak()
      #text(size: 9pt, style: "italic")[#subtitle]
    ]
  ]
  v(8pt)
}

#let nature-section(name, content) = {
  heading(level: 1, name)
  content
}

#let figure-note(label, title, path) = {
  block[
    #text(weight: "bold")[#label.] #title \
    #text(size: 8pt)[Source: #path]
  ]
}
