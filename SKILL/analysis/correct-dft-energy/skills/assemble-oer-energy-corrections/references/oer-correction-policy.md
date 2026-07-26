# OER correction and interpretation policy

## O2 reference

For a documented standard state, define:

\[
G_{O_2}^{cycle}=2G_{H_2O}-2G_{H_2}+\Delta G_{2H_2O\rightarrow O_2+2H_2}^{exp}.
\]

At 298.15 K, the commonly used standard-state value is 4.92 eV per O2. The skill requires the value to be supplied in the input or CLI and records its temperature and provenance. It is not silently added to a direct O2 energy.

## Step energies

With `mu_pair = 1/2 G(H2) - eU_RHE`:

\[
\Delta G_1=G_{OH*}+\mu_{pair}-G_*-G_{H_2O}
\]

\[
\Delta G_2=G_{O*}+\mu_{pair}-G_{OH*}
\]

\[
\Delta G_3=G_{OOH*}+\mu_{pair}-G_{O*}-G_{H_2O}
\]

\[
\Delta G_4=G_*+G_{O_2}+\mu_{pair}-G_{OOH*}.
\]

On SHE, use `mu_pair = 1/2 G(H2) - eU_SHE - kBT ln(10) pH`.

## Closure

At zero RHE potential, the four steps must sum to the selected cycle free energy. On SHE, the explicit pH term changes the zero-potential overall free energy by `-4 kBT ln(10) pH`.

## Model boundary

The script assumes identical catalyst/support stoichiometry across `clean`, `OH`, `O`, and `OOH`. A lattice-oxygen mechanism, oxygen-vacancy reservoir, dissolution, or changing bulk oxidation state requires an explicit reaction network and chemical potentials rather than this bounded AEM calculator.
