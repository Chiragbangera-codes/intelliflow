import { Metadata } from "next";
import { RegisterForm } from "@/features/auth";

export const metadata: Metadata = {
  title: "Register",
  description: "Create a new IntelliFlow AI account",
};

export default function RegisterPage() {
  return <RegisterForm />;
}
