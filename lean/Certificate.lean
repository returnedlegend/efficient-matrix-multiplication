import Std

/- Exact bilinear tensor certificates over F₂, represented by Bool with xor/and.
   No floating point, axioms, or sorry. This file does not assert a rank-94 result. -/
namespace MatrixCertificate

def sum (xs : List α) (f : α → Bool) : Bool :=
  xs.foldr (fun x acc => f x ^^ acc) false

@[simp] theorem sum_nil (f : α → Bool) : sum [] f = false := rfl
@[simp] theorem sum_cons (x : α) (xs : List α) (f : α → Bool) :
    sum (x :: xs) f = (f x ^^ sum xs f) := rfl

theorem xor_reorder (a b c d : Bool) :
    ((a ^^ b) ^^ (c ^^ d)) = ((a ^^ c) ^^ (b ^^ d)) := by
  cases a <;> cases b <;> cases c <;> cases d <;> decide

theorem and_xor (a b c : Bool) : ((a ^^ b) && c) = ((a && c) ^^ (b && c)) := by
  cases a <;> cases b <;> cases c <;> decide

theorem xor_and (a b c : Bool) : (a && (b ^^ c)) = ((a && b) ^^ (a && c)) := by
  cases a <;> cases b <;> cases c <;> decide

theorem sum_xor (xs : List α) (f g : α → Bool) :
    sum xs (fun x => f x ^^ g x) = (sum xs f ^^ sum xs g) := by
  induction xs with
  | nil => rfl
  | cons x xs ih =>
    simp only [sum_cons, ih]
    exact xor_reorder _ _ _ _

theorem sum_and (xs : List α) (f : α → Bool) (b : Bool) :
    sum xs (fun x => f x && b) = (sum xs f && b) := by
  induction xs with
  | nil => cases b <;> rfl
  | cons x xs ih => simp only [sum_cons, ih, and_xor]

theorem and_sum (xs : List α) (f : α → Bool) (b : Bool) :
    sum xs (fun x => b && f x) = (b && sum xs f) := by
  induction xs with
  | nil => cases b <;> rfl
  | cons x xs ih => simp only [sum_cons, ih, xor_and]

theorem sum_swap (xs : List α) (ys : List β) (f : α → β → Bool) :
    sum xs (fun x => sum ys (fun y => f x y)) =
    sum ys (fun y => sum xs (fun x => f x y)) := by
  induction xs with
  | nil =>
    simp only [sum_nil]
    induction ys with
    | nil => rfl
    | cons y ys ih =>
      change false = (false ^^ sum ys (fun _ => false))
      rw [← ih]
      rfl
  | cons x xs ih =>
    simp only [sum_cons]
    rw [ih]
    exact (sum_xor ys (fun y => f x y) (fun y => sum xs (fun x => f x y))).symm

theorem sum_congr (xs : List α) {f g : α → Bool} (h : ∀ x, f x = g x) :
    sum xs f = sum xs g := by
  have : f = g := funext h
  rw [this]

-- Rank-R straight-line bilinear algorithm: R products of linear forms.
def algorithm (xs : List α) (ys : List β) (rs : List ρ)
    (U : ρ → α → Bool) (V : ρ → β → Bool) (W : ρ → γ → Bool)
    (A : α → Bool) (B : β → Bool) (c : γ) : Bool :=
  sum rs (fun r =>
    (sum xs (fun a => U r a && A a)) &&
    (sum ys (fun b => V r b && B b)) && W r c)

def contraction (xs : List α) (ys : List β)
    (T : α → β → γ → Bool) (A : α → Bool) (B : β → Bool) (c : γ) : Bool :=
  sum xs (fun a => sum ys (fun b => T a b c && A a && B b))

-- The certificate premise is the full exact coefficient equality, not random testing.
theorem certificate_correct (xs : List α) (ys : List β) (rs : List ρ)
    (U : ρ → α → Bool) (V : ρ → β → Bool) (W : ρ → γ → Bool)
    (T : α → β → γ → Bool)
    (certificate : ∀ a b c, sum rs (fun r => U r a && V r b && W r c) = T a b c)
    (A : α → Bool) (B : β → Bool) (c : γ) :
    algorithm xs ys rs U V W A B c = contraction xs ys T A B c := by
  unfold algorithm contraction
  calc
    _ = sum rs (fun r => sum xs (fun a => sum ys (fun b =>
      (U r a && V r b && W r c) && A a && B b))) := by
      apply sum_congr
      intro r
      rw [← sum_and, ← sum_and]
      apply sum_congr
      intro a
      rw [← and_sum]
      rw [← sum_and]
      apply sum_congr
      intro b
      cases U r a <;> cases V r b <;> cases W r c <;>
        cases A a <;> cases B b <;> decide
    _ = sum xs (fun a => sum ys (fun b => sum rs (fun r =>
      (U r a && V r b && W r c) && A a && B b))) := by
      rw [sum_swap rs xs]
      apply sum_congr
      intro a
      exact sum_swap rs ys _
    _ = _ := by
      apply sum_congr
      intro a
      apply sum_congr
      intro b
      rw [sum_and, sum_and, certificate]

-- Trace convention: A[i,j] B[j,k] W[k,i]. Output C[i,k] uses c=(k,i).
abbrev Index := Fin 5 × Fin 5

def target (a b c : Index) : Bool :=
  decide (a.2 = b.1 ∧ b.2 = c.1 ∧ c.2 = a.1)

def indices : List Index :=
  (List.finRange 5).flatMap (fun i => (List.finRange 5).map (fun j => (i,j)))

def matmul (A B : Index → Bool) (i k : Fin 5) : Bool :=
  sum (List.finRange 5) (fun j => A (i,j) && B (j,k))

theorem contraction_target (A B : Index → Bool) (i k : Fin 5) :
    contraction indices indices target A B (k,i) = matmul A B i k := by
  obtain ⟨i, hi⟩ := i
  obtain ⟨k, hk⟩ := k
  have hi' : i = 0 ∨ i = 1 ∨ i = 2 ∨ i = 3 ∨ i = 4 := by omega
  have hk' : k = 0 ∨ k = 1 ∨ k = 2 ∨ k = 3 ∨ k = 4 := by omega
  rcases hi' with h | h | h | h | h <;> subst i <;>
    rcases hk' with h | h | h | h | h <;> subst k <;>
    simp [contraction, target, indices, matmul, sum, List.finRange]

theorem matrix_multiplication_correct (rs : List ρ)
    (U V W : ρ → Index → Bool)
    (certificate : ∀ a b c, sum rs (fun r => U r a && V r b && W r c) = target a b c)
    (A B : Index → Bool) (i k : Fin 5) :
    algorithm indices indices rs U V W A B (k,i) = matmul A B i k := by
  rw [certificate_correct indices indices rs U V W target certificate A B (k,i)]
  exact contraction_target A B i k

-- An explicit finite decomposition must still discharge certificate above.
end MatrixCertificate
