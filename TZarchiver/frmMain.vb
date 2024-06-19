Imports System.IO

Public Class frmMain

    Dim fileList As New List(Of String)

    Private Sub frmMain_DragDrop(sender As Object, e As DragEventArgs) Handles Me.DragDrop
        Dim files As String() = e.Data.GetData(DataFormats.FileDrop)
        For Each file As String In files
            lstArchives.Items.Add(Path.GetFileName(file))
            lstArchives.SelectedIndex = lstArchives.Items.Count - 1
            fileList.Add(file)
        Next
        ExtractTZarc(False)
    End Sub

    Private Sub frmMain_DragEnter(sender As Object, e As DragEventArgs) Handles Me.DragEnter
        If e.Data.GetDataPresent(DataFormats.FileDrop) Then
            e.Effect = DragDropEffects.Copy
        End If
    End Sub

    ''' <summary>
    ''' Extract files from a TZarc archive
    ''' </summary>
    ''' <param name="mode">Specifies if files are also extracted or only read</param>
    Sub ExtractTZarc(mode As Boolean)
        Dim currentTZarc As Integer = 0
        tvContents.Nodes.Clear()

        For Each file As String In fileList

            If My.Computer.FileSystem.FileExists(file) Then 'extract tzarc
                Dim FileStr As BinaryReader

                Try
                    FileStr = New BinaryReader(IO.File.Open(file, FileMode.Open))
                    FileStr.BaseStream.Seek(0, SeekOrigin.Begin)

                    Dim ExpectedSignature As Byte() = System.Text.Encoding.ASCII.GetBytes("TZac")
                    Dim FileSignature(ExpectedSignature.Length - 1) As Byte

                    FileSignature = FileStr.ReadBytes(ExpectedSignature.Length)

                    If Not CompareBytes(FileSignature, ExpectedSignature) Then
                        FileStr.Close()
                        Throw New Exception("File format not supported for " & file)
                    End If

                    Dim fileVersion As UInteger = ParseUInt32(FileStr.ReadBytes(4))
                    If fileVersion <> 1 Then
                        FileStr.Close()
                        Throw New Exception("TZarc version " & fileVersion & " is not supported!")
                    End If

                    tvContents.Nodes.Add(Path.GetFileName(file))

                    Dim fileCount As UInteger = ParseUInt32(FileStr.ReadBytes(4))

                    Dim filesInside As New List(Of FileInfo)

                    For i As Integer = 0 To fileCount - 1
                        Dim currentFile As New FileInfo
                        Dim fNameSize As Byte

                        fNameSize = FileStr.ReadByte

                        Dim fileName(fNameSize - 1) As Byte
                        Array.Copy(FileStr.ReadBytes(fNameSize), 0, fileName, 0, fNameSize)
                        currentFile.fileName = System.Text.Encoding.UTF8.GetString(fileName)

                        tvContents.Nodes(currentTZarc).Nodes.Add(currentFile.fileName)

                        currentFile.fileLength = ParseUInt64(FileStr.ReadBytes(8))
                        filesInside.Add(currentFile)
                    Next

                    FileStr.ReadUInt32() 'skip random time data

                    Dim currentPath As String = Path.GetDirectoryName(file) & "\" & Path.GetFileNameWithoutExtension(file)
                    If mode Then My.Computer.FileSystem.CreateDirectory(currentPath)

                    If mode Then
                        For Each fis In filesInside
                            Dim currentData(fis.fileLength - 1) As Byte
                            If fis.fileLength > Integer.MaxValue Then
                                FileStr.Close()
                                Throw New Exception("Internal filesize for " & fis.fileName & " exceeds " & Integer.MaxValue & " !")
                            End If
                            Array.Copy(FileStr.ReadBytes(fis.fileLength), 0, currentData, 0, CInt(fis.fileLength))

                            'ensure we have all the subdirectories required
                            If fis.fileName.Contains("/") Then
                                Directory.CreateDirectory(Path.GetDirectoryName(currentPath & "\" & fis.fileName))
                            End If
                            My.Computer.FileSystem.WriteAllBytes(currentPath & "\" & fis.fileName, currentData, False)
                        Next
                    End If

                    tvContents.Nodes(currentTZarc).Expand()
                    currentTZarc = currentTZarc + 1

                    FileStr.Close()

                Catch ex As Exception
                    MessageBox.Show(ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error)
                End Try

            End If
        Next
        If mode Then MessageBox.Show("Finished extracting files", "Ready", MessageBoxButtons.OK, MessageBoxIcon.Information)
    End Sub


    Private Sub btnExtract_Click(sender As Object, e As EventArgs) Handles btnExtract.Click
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

    Function ParseUInt32(ByRef b As Byte()) As UInteger
        Return BitConverter.ToUInt32(RevHex(b, 0, 4), 0)
    End Function

    Function ParseUInt64(ByRef b As Byte()) As ULong
        Return BitConverter.ToUInt64(RevHex(b, 0, 8), 0)
    End Function

    Function ToInteger32(ByVal i As Integer) As Byte()
        Return RevHex(BitConverter.GetBytes(i), 0, 4)
    End Function

    Function ToInteger64(ByVal i As Long) As Byte()
        Return RevHex(BitConverter.GetBytes(i), 0, 8)
    End Function

    Private Sub btnRemove_Click(sender As Object, e As EventArgs) Handles btnRemove.Click
        If lstArchives.SelectedItem = Nothing Then Exit Sub
        fileList.RemoveAt(lstArchives.SelectedIndex)
        tvContents.Nodes(lstArchives.SelectedIndex).Remove()
        lstArchives.Items.RemoveAt(lstArchives.SelectedIndex)
        lstArchives.SelectedIndex = lstArchives.Items.Count - 1
    End Sub

    Private Sub btnCreate_Click(sender As Object, e As EventArgs) Handles btnCreate.Click
        Dim currentTZarc As Integer = 0

        For Each file As String In fileList

            If Not My.Computer.FileSystem.FileExists(file) Then 'create tzarc

                Try
                    Dim bytes As New List(Of Byte)
                    bytes.AddRange(System.Text.Encoding.ASCII.GetBytes("TZac"))

                    Dim filesToAdd As String() = Directory.GetFiles(file, "*", SearchOption.AllDirectories)

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

    Private Sub btnClear_Click(sender As Object, e As EventArgs) Handles btnClear.Click
        lstArchives.Items.Clear()
        tvContents.Nodes.Clear()
        fileList.Clear()
    End Sub

    Private Sub frmMain_Load(sender As Object, e As EventArgs) Handles MyBase.Load
        Dim files As String() = My.Application.CommandLineArgs.ToArray
        If files.Length > 0 Then
            For Each file As String In files
                lstArchives.Items.Add(Path.GetFileName(file))
                lstArchives.SelectedIndex = lstArchives.Items.Count - 1
                fileList.Add(file)
            Next
            ExtractTZarc(False)
        End If
    End Sub

    Private Sub lnkGitHub_LinkClicked(sender As Object, e As LinkLabelLinkClickedEventArgs) Handles lnkGitHub.LinkClicked
        Process.Start("https://github.com/SilverGreen93/TZarchiver")
    End Sub

    'a new instance of the application was started with new arguments
    Public Sub NewArgumentsReceived(args As String())
        If args.Length > 0 Then
            Dim files As String() = args.ToArray
            For Each file As String In files
                lstArchives.Items.Add(Path.GetFileName(file))
                lstArchives.SelectedIndex = lstArchives.Items.Count - 1
                fileList.Add(file)
            Next
            ExtractTZarc(False)
        End If
    End Sub

End Class
