Public Class Form1

    Dim fileList As New List(Of String)

    Private Sub Form1_DragDrop(sender As Object, e As DragEventArgs) Handles Me.DragDrop
        Dim files As String() = e.Data.GetData(DataFormats.FileDrop)
        For Each file As String In files
            ListBox1.Items.Add(System.IO.Path.GetFileName(file))
            ListBox1.SelectedIndex = ListBox1.Items.Count - 1
            fileList.Add(file)
        Next
        ExtractTZarc(False)
    End Sub

    Private Sub Form1_DragEnter(sender As Object, e As DragEventArgs) Handles Me.DragEnter
        If e.Data.GetDataPresent(DataFormats.FileDrop) Then
            e.Effect = DragDropEffects.Copy
        End If
    End Sub

    Sub ExtractTZarc(mode As Boolean)
        Dim currentTZarc As Integer = 0
        TreeView1.Nodes.Clear()

        For Each file As String In fileList

            If My.Computer.FileSystem.FileExists(file) Then 'extract tzarc

                Try
                    TreeView1.Nodes.Add(System.IO.Path.GetFileName(file))

                    Dim bytes As Byte() = My.Computer.FileSystem.ReadAllBytes(file)

                    Dim b1(3) As Byte
                    Array.Copy(bytes, b1, 4)
                    Dim b2 As Byte() = System.Text.Encoding.ASCII.GetBytes("TZac")

                    If Not CompareBytes(b1, b2) Then
                        MessageBox.Show("File format not supported for " & file, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                        Continue For
                    End If

                    Dim fpointer As Integer = 4
                    Dim fileVersion As Integer = ParseInteger32(bytes, fpointer)
                    If fileVersion <> 1 Then
                        MessageBox.Show("TZarc version " & fileVersion & " is not supported!", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                        Continue For
                    End If

                    fpointer = fpointer + 4

                    Dim fileCount As Integer = ParseInteger32(bytes, fpointer)

                    fpointer = fpointer + 4

                    Dim filesInside As New List(Of FileInfo)

                    For i As Integer = 0 To fileCount - 1
                        Dim currentFile As New FileInfo
                        Dim fNameSize As Byte

                        fNameSize = bytes(fpointer)
                        fpointer = fpointer + 1

                        Dim fileName(fNameSize - 1) As Byte
                        Array.Copy(bytes, fpointer, fileName, 0, fNameSize)
                        currentFile.fileName = System.Text.Encoding.UTF8.GetString(fileName)

                        fpointer = fpointer + fNameSize

                        TreeView1.Nodes(currentTZarc).Nodes.Add(currentFile.fileName)

                        currentFile.fileLength = ParseInteger64(bytes, fpointer)
                        fpointer = fpointer + 8
                        filesInside.Add(currentFile)

                    Next

                    fpointer = fpointer + 4 'skip random time data

                    Dim currentPath As String = System.IO.Path.GetDirectoryName(file) & "\" & System.IO.Path.GetFileNameWithoutExtension(file)
                    If mode Then My.Computer.FileSystem.CreateDirectory(currentPath)

                    If mode Then
                        For Each fis In filesInside
                            Dim currentData(fis.fileLength - 1) As Byte
                            Array.Copy(bytes, fpointer, currentData, 0, fis.fileLength)
                            fpointer = fpointer + fis.fileLength

                            'ensure we have all the subdirectories required
                            If fis.fileName.Contains("/") Then
                                System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(currentPath & "\" & fis.fileName))
                            End If
                            My.Computer.FileSystem.WriteAllBytes(currentPath & "\" & fis.fileName, currentData, False)
                        Next
                    End If

                    TreeView1.Nodes(currentTZarc).Expand()
                    currentTZarc = currentTZarc + 1

                Catch ex As Exception
                    MessageBox.Show(ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                End Try

            End If
        Next
        If mode Then MessageBox.Show("Finished extracting files", "Ready", MessageBoxButtons.OK, MessageBoxIcon.Information)
    End Sub


    Private Sub Button1_Click(sender As Object, e As EventArgs) Handles Button1.Click
        ExtractTZarc(True)
    End Sub

    Function CompareBytes(ByVal b1 As Byte(), ByVal b2 As Byte()) As Boolean
        If (b1 Is b2) Then
            Return True
        End If
        If (b1 Is Nothing OrElse b2 Is Nothing) Then
            Return False
        End If
        If (b1.Length <> b2.Length) Then
            Return False
        End If
        For i As Integer = 0 To b1.Length - 1
            If (b1(i) <> b2(i)) Then
                Return False
            End If
        Next i
        Return True
    End Function

    Function RevHex(ByRef b As Byte(), ByVal start As Integer, ByVal len As Integer) As Byte()

        Dim rbytes(len - 1) As Byte   'returned bytes

        'reverse bytes (a-b-c-d-e-f-g-h -> h-g-f-e-d-c-b-a)
        For i As Integer = 0 To len - 1
            rbytes(i) = b(start + len - 1 - i)
        Next

        Return rbytes

    End Function

    Function ParseInteger32(ByRef b As Byte(), ByVal pos As Integer) As Integer
        Return BitConverter.ToInt32(RevHex(b, pos, 4), 0)
    End Function

    Function ParseInteger64(ByRef b As Byte(), ByVal pos As Integer) As Long
        Return BitConverter.ToInt64(RevHex(b, pos, 8), 0)
    End Function

    Function ToInteger32(ByVal i As Integer) As Byte()
        Return RevHex(BitConverter.GetBytes(i), 0, 4)
    End Function

    Function ToInteger64(ByVal i As Long) As Byte()
        Return RevHex(BitConverter.GetBytes(i), 0, 8)
    End Function

    Private Sub Button3_Click(sender As Object, e As EventArgs) Handles Button3.Click
        If ListBox1.SelectedItem = Nothing Then Exit Sub
        fileList.RemoveAt(ListBox1.SelectedIndex)
        TreeView1.Nodes(ListBox1.SelectedIndex).Remove()
        ListBox1.Items.RemoveAt(ListBox1.SelectedIndex)
        ListBox1.SelectedIndex = ListBox1.Items.Count - 1
    End Sub

    Private Sub Button2_Click(sender As Object, e As EventArgs) Handles Button2.Click
        Dim currentTZarc As Integer = 0

        For Each file As String In fileList

            If Not My.Computer.FileSystem.FileExists(file) Then 'create tzarc

                Try
                    Dim bytes As New List(Of Byte)
                    bytes.AddRange(System.Text.Encoding.ASCII.GetBytes("TZac"))

                    Dim filesToAdd As String() = System.IO.Directory.GetFiles(file, "*", System.IO.SearchOption.AllDirectories)

                    Dim fileCount As Integer = filesToAdd.Length
                    bytes.AddRange({0, 0, 0, 1})
                    bytes.AddRange(ToInteger32(fileCount))

                    For i As Integer = 0 To fileCount - 1
                        Dim fn As String 'make sure to add subdirectories to filename
                        fn = Strings.Right(filesToAdd(i), filesToAdd(i).Length - file.Length - 1)
                        fn = Replace(fn, "\", "/")
                        bytes.Add(ToInteger32(fn.Length)(3))
                        bytes.AddRange(System.Text.Encoding.UTF8.GetBytes(fn))
                        bytes.AddRange(ToInteger64(My.Computer.FileSystem.GetFileInfo(filesToAdd(i)).Length))
                    Next

                    bytes.AddRange({125, 47, 13, 99}) 'random time data

                    For i As Integer = 0 To fileCount - 1
                        bytes.AddRange(My.Computer.FileSystem.ReadAllBytes(filesToAdd(i)))
                    Next

                    My.Computer.FileSystem.WriteAllBytes(file & ".tzarc", bytes.ToArray, False)
                    currentTZarc = currentTZarc + 1

                Catch ex As Exception
                    MessageBox.Show(ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                End Try

            End If
        Next
        MessageBox.Show("Finished creating archives", "Ready", MessageBoxButtons.OK, MessageBoxIcon.Information)
    End Sub

    Private Sub Button4_Click(sender As Object, e As EventArgs) Handles Button4.Click
        ListBox1.Items.Clear()
        TreeView1.Nodes.Clear()
        fileList.Clear()
    End Sub

    Private Sub Form1_Load(sender As Object, e As EventArgs) Handles MyBase.Load
        Dim files As String() = My.Application.CommandLineArgs.ToArray
        If files.Length > 0 Then
            For Each file As String In files
                ListBox1.Items.Add(System.IO.Path.GetFileName(file))
                ListBox1.SelectedIndex = ListBox1.Items.Count - 1
                fileList.Add(file)
            Next
            ExtractTZarc(False)
        End If
    End Sub

    Private Sub LinkLabel1_LinkClicked(sender As Object, e As LinkLabelLinkClickedEventArgs) Handles LinkLabel1.LinkClicked
        Process.Start("http://vvmm.freeforums.org/")
    End Sub

    'a new instance of the application was started with new arguments
    Public Sub NewArgumentsReceived(args As String())
        If args.Length > 0 Then
            Dim files As String() = args.ToArray
            For Each file As String In files
                ListBox1.Items.Add(System.IO.Path.GetFileName(file))
                ListBox1.SelectedIndex = ListBox1.Items.Count - 1
                fileList.Add(file)
            Next
            ExtractTZarc(False)
        End If
    End Sub

End Class
